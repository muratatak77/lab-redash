from flask import request
from funcy import project

from redash import models, utils
from redash.handlers.base import (
    BaseResource,
    get_object_or_404,
    paginate,
    require_fields,
)
from redash.permissions import (
    require_access,
    require_admin_or_owner,
    require_permission,
    view_only,
)
from redash.serializers import serialize_alert
from redash.tasks.alerts import (
    notify_subscriptions,
    should_notify,
)


class AlertResource(BaseResource):
    def get(self, alert_id):
        alert = get_object_or_404(models.Alert.get_by_id_and_org, alert_id, self.current_org)
        require_access(alert, self.current_user, view_only)
        self.record_event({"action": "view", "object_id": alert.id, "object_type": "alert"})
        return serialize_alert(alert)

    def post(self, alert_id):
        req = request.get_json(True)
        params = project(req, ("options", "name", "query_id", "rearm"))
        alert = get_object_or_404(models.Alert.get_by_id_and_org, alert_id, self.current_org)
        require_admin_or_owner(alert.user.id)

        if "query_id" in params:
            query = get_object_or_404(models.Query.get_by_id_and_org, params.pop("query_id"), self.current_org)
        else:
            query = alert.query_rel
        require_access(query, self.current_user, view_only)
        alert.query_rel = query

        self.update_model(alert, params)
        models.db.session.commit()

        self.record_event({"action": "edit", "object_id": alert.id, "object_type": "alert"})

        return serialize_alert(alert)

    def delete(self, alert_id):
        alert = get_object_or_404(models.Alert.get_by_id_and_org, alert_id, self.current_org)
        require_admin_or_owner(alert.user_id)
        models.db.session.delete(alert)
        models.db.session.commit()


class AlertEvaluateResource(BaseResource):
    def post(self, alert_id):
        alert = get_object_or_404(models.Alert.get_by_id_and_org, alert_id, self.current_org)
        require_admin_or_owner(alert.user.id)
        require_access(alert, self.current_user, view_only)

        value = alert.current_value()
        new_state = alert.evaluate(value)
        if should_notify(alert, new_state):
            alert.record_state_change(
                alert.state,
                new_state,
                notified=True,
                trigger=models.AlertStateChange.MANUAL_TRIGGER,
                value=value,
            )
            alert.state = new_state
            alert.last_triggered_at = utils.utcnow()
            models.db.session.commit()

        notify_subscriptions(alert, new_state, {})
        self.record_event({"action": "evaluate", "object_id": alert.id, "object_type": "alert"})


class AlertMuteResource(BaseResource):
    def post(self, alert_id):
        alert = get_object_or_404(models.Alert.get_by_id_and_org, alert_id, self.current_org)
        require_admin_or_owner(alert.user.id)

        alert.options["muted"] = True
        models.db.session.commit()

        self.record_event({"action": "mute", "object_id": alert.id, "object_type": "alert"})

    def delete(self, alert_id):
        alert = get_object_or_404(models.Alert.get_by_id_and_org, alert_id, self.current_org)
        require_admin_or_owner(alert.user.id)

        alert.options["muted"] = False
        models.db.session.commit()

        self.record_event({"action": "unmute", "object_id": alert.id, "object_type": "alert"})


class AlertStateHistoryResource(BaseResource):
    def get(self, alert_id):
        """
        Lists the state changes of an alert, most recent first.

        :qparam number page: Page number to retrieve.
        :qparam number page_size: Number of state changes to return per page.
        """
        alert = get_object_or_404(models.Alert.get_by_id_and_org, alert_id, self.current_org)
        require_access(alert, self.current_user, view_only)

        page = request.args.get("page", 1, type=int)
        page_size = request.args.get("page_size", 25, type=int)

        self.record_event({"action": "view_history", "object_id": alert.id, "object_type": "alert"})

        return paginate(
            models.AlertStateChange.for_alert(alert.id),
            page,
            page_size,
            lambda change: change.to_dict(),
        )


class AlertListResource(BaseResource):
    def post(self):
        req = request.get_json(True)
        require_fields(req, ("options", "name", "query_id"))

        query = models.Query.get_by_id_and_org(req["query_id"], self.current_org)
        require_access(query, self.current_user, view_only)

        alert = models.Alert(
            name=req["name"],
            query_rel=query,
            user=self.current_user,
            rearm=req.get("rearm"),
            options=req["options"],
        )

        models.db.session.add(alert)
        models.db.session.flush()
        models.db.session.commit()

        self.record_event({"action": "create", "object_id": alert.id, "object_type": "alert"})

        return serialize_alert(alert)

    @require_permission("list_alerts")
    def get(self):
        self.record_event({"action": "list", "object_type": "alert"})
        return [serialize_alert(alert) for alert in models.Alert.all(group_ids=self.current_user.group_ids)]


class AlertSubscriptionListResource(BaseResource):
    def post(self, alert_id):
        req = request.get_json(True)

        alert = models.Alert.get_by_id_and_org(alert_id, self.current_org)
        require_access(alert, self.current_user, view_only)
        kwargs = {"alert": alert, "user": self.current_user}

        if "destination_id" in req:
            destination = models.NotificationDestination.get_by_id_and_org(req["destination_id"], self.current_org)
            kwargs["destination"] = destination

        subscription = models.AlertSubscription(**kwargs)
        models.db.session.add(subscription)
        models.db.session.commit()

        self.record_event(
            {
                "action": "subscribe",
                "object_id": alert_id,
                "object_type": "alert",
                "destination": req.get("destination_id"),
            }
        )

        d = subscription.to_dict()
        return d

    def get(self, alert_id):
        alert = models.Alert.get_by_id_and_org(alert_id, self.current_org)
        require_access(alert, self.current_user, view_only)

        subscriptions = models.AlertSubscription.all(alert_id)
        return [s.to_dict() for s in subscriptions]


class AlertSubscriptionResource(BaseResource):
    def delete(self, alert_id, subscriber_id):
        subscription = models.AlertSubscription.query.get_or_404(subscriber_id)
        require_admin_or_owner(subscription.user.id)
        models.db.session.delete(subscription)
        models.db.session.commit()

        self.record_event({"action": "unsubscribe", "object_id": alert_id, "object_type": "alert"})
