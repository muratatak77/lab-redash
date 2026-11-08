import datetime

from mock import ANY, MagicMock, patch

import redash.tasks.alerts
from redash.models import Alert, AlertStateChange
from redash.tasks.alerts import check_alerts_for_query, notify_subscriptions
from redash.utils import utcnow
from tests import BaseTestCase


class TestCheckAlertsForQuery(BaseTestCase):
    def test_notifies_subscribers_when_should(self):
        redash.tasks.alerts.notify_subscriptions = MagicMock()
        Alert.evaluate = MagicMock(return_value=Alert.TRIGGERED_STATE)

        alert = self.factory.create_alert()
        check_alerts_for_query(alert.query_id, metadata={"Scheduled": False})

        self.assertTrue(redash.tasks.alerts.notify_subscriptions.called)

    def test_doesnt_notify_when_nothing_changed(self):
        redash.tasks.alerts.notify_subscriptions = MagicMock()
        Alert.evaluate = MagicMock(return_value=Alert.OK_STATE)

        alert = self.factory.create_alert()
        check_alerts_for_query(alert.query_id, metadata={"Scheduled": False})

        self.assertFalse(redash.tasks.alerts.notify_subscriptions.called)

    def test_doesnt_notify_when_muted(self):
        redash.tasks.alerts.notify_subscriptions = MagicMock()
        Alert.evaluate = MagicMock(return_value=Alert.TRIGGERED_STATE)

        alert = self.factory.create_alert(options={"muted": True})
        check_alerts_for_query(alert.query_id, metadata={"Scheduled": False})

        self.assertFalse(redash.tasks.alerts.notify_subscriptions.called)


@patch("redash.tasks.alerts.notify_subscriptions")
class TestCheckAlertsForQueryHistory(BaseTestCase):
    def check(self, alert, new_state):
        with patch.object(Alert, "evaluate", return_value=new_state):
            check_alerts_for_query(alert.query_id, metadata={"Scheduled": True})
        return list(AlertStateChange.for_alert(alert.id))

    def test_records_state_change_when_notifying(self, notify_subscriptions):
        alert = self.factory.create_alert(state=Alert.OK_STATE)

        (change,) = self.check(alert, Alert.TRIGGERED_STATE)

        self.assertEqual(change.previous_state, Alert.OK_STATE)
        self.assertEqual(change.new_state, Alert.TRIGGERED_STATE)
        self.assertTrue(change.notified)
        self.assertEqual(change.trigger, AlertStateChange.SCHEDULED_TRIGGER)
        notify_subscriptions.assert_called_once()

    def test_records_state_change_of_muted_alert_as_not_notified(self, notify_subscriptions):
        alert = self.factory.create_alert(state=Alert.OK_STATE, options={"muted": True})

        (change,) = self.check(alert, Alert.TRIGGERED_STATE)

        self.assertFalse(change.notified)
        notify_subscriptions.assert_not_called()

    def test_records_first_ok_evaluation_as_not_notified(self, notify_subscriptions):
        alert = self.factory.create_alert()

        (change,) = self.check(alert, Alert.OK_STATE)

        self.assertEqual(change.previous_state, Alert.UNKNOWN_STATE)
        self.assertFalse(change.notified)
        notify_subscriptions.assert_not_called()

    def test_doesnt_record_anything_when_state_is_unchanged(self, notify_subscriptions):
        alert = self.factory.create_alert(state=Alert.OK_STATE)

        self.assertEqual([], self.check(alert, Alert.OK_STATE))

    def test_records_rearmed_notification(self, notify_subscriptions):
        alert = self.factory.create_alert(
            state=Alert.TRIGGERED_STATE,
            rearm=60,
            last_triggered_at=utcnow() - datetime.timedelta(minutes=5),
        )

        (change,) = self.check(alert, Alert.TRIGGERED_STATE)

        self.assertEqual(change.previous_state, Alert.TRIGGERED_STATE)
        self.assertEqual(change.new_state, Alert.TRIGGERED_STATE)
        self.assertTrue(change.notified)


class TestNotifySubscriptions(BaseTestCase):
    def test_calls_notify_for_subscribers(self):
        subscription = self.factory.create_alert_subscription()
        subscription.notify = MagicMock()
        notify_subscriptions(subscription.alert, Alert.OK_STATE, metadata={"Scheduled": False})
        subscription.notify.assert_called_with(
            subscription.alert,
            subscription.alert.query_rel,
            subscription.user,
            Alert.OK_STATE,
            ANY,
            ANY,
            ANY,
        )
