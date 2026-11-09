import textwrap
from unittest import TestCase

from mock import patch

from redash import settings
from redash.models import OPERATORS, Alert, AlertStateChange, db, next_state
from tests import BaseTestCase


class TestAlertAll(BaseTestCase):
    def test_returns_all_alerts_for_given_groups(self):
        ds1 = self.factory.data_source
        group = self.factory.create_group()
        ds2 = self.factory.create_data_source(group=group)

        query1 = self.factory.create_query(data_source=ds1)
        query2 = self.factory.create_query(data_source=ds2)

        alert1 = self.factory.create_alert(query_rel=query1)
        alert2 = self.factory.create_alert(query_rel=query2)
        db.session.flush()

        alerts = Alert.all(group_ids=[group.id, self.factory.default_group.id])
        self.assertIn(alert1, alerts)
        self.assertIn(alert2, alerts)

        alerts = Alert.all(group_ids=[self.factory.default_group.id])
        self.assertIn(alert1, alerts)
        self.assertNotIn(alert2, alerts)

        alerts = Alert.all(group_ids=[group.id])
        self.assertNotIn(alert1, alerts)
        self.assertIn(alert2, alerts)

    def test_return_each_alert_only_once(self):
        group = self.factory.create_group()
        self.factory.data_source.add_group(group)

        alert = self.factory.create_alert()

        alerts = Alert.all(group_ids=[self.factory.default_group.id, group.id])
        self.assertEqual(1, len(list(alerts)))
        self.assertIn(alert, alerts)


def get_results(value):
    return {"rows": [{"foo": value}], "columns": [{"name": "foo", "type": "STRING"}]}


class TestAlertEvaluate(BaseTestCase):
    def create_alert(self, results, column="foo", value="1"):
        result = self.factory.create_query_result(data=results)
        query = self.factory.create_query(latest_query_data_id=result.id)
        alert = self.factory.create_alert(
            query_rel=query, options={"selector": "first", "op": "equals", "column": column, "value": value}
        )
        return alert

    def test_evaluate_triggers_alert_when_equal(self):
        alert = self.create_alert(get_results(1))
        self.assertEqual(alert.evaluate(), Alert.TRIGGERED_STATE)

    def test_evaluate_number_value_and_string_threshold(self):
        alert = self.create_alert(get_results(1), value="string")
        self.assertEqual(alert.evaluate(), Alert.UNKNOWN_STATE)

    def test_evaluate_return_unknown_when_missing_column(self):
        alert = self.create_alert(get_results(1), column="bar")
        self.assertEqual(alert.evaluate(), Alert.UNKNOWN_STATE)

    def test_evaluate_return_unknown_when_empty_results(self):
        results = {"rows": [], "columns": [{"name": "foo", "type": "STRING"}]}
        alert = self.create_alert(results)
        self.assertEqual(alert.evaluate(), Alert.UNKNOWN_STATE)

    def test_evaluates_correctly_with_first_selector(self):
        results = {"rows": [{"foo": 1}, {"foo": 2}], "columns": [{"name": "foo", "type": "INTEGER"}]}
        alert = self.create_alert(results)
        alert.options["selector"] = "first"
        self.assertEqual(alert.evaluate(), Alert.TRIGGERED_STATE)
        results = {
            "rows": [{"foo": "test"}, {"foo": "test"}, {"foo": "test"}],
            "columns": [{"name": "foo", "type": "STRING"}],
        }
        alert = self.create_alert(results)
        alert.options["selector"] = "first"
        alert.options["op"] = "<"
        self.assertEqual(alert.evaluate(), Alert.UNKNOWN_STATE)

    def test_evaluates_correctly_with_min_selector(self):
        results = {"rows": [{"foo": 2}, {"foo": 1}], "columns": [{"name": "foo", "type": "INTEGER"}]}
        alert = self.create_alert(results)
        alert.options["selector"] = "min"
        self.assertEqual(alert.evaluate(), Alert.TRIGGERED_STATE)
        results = {
            "rows": [{"foo": "test"}, {"foo": "test"}, {"foo": "test"}],
            "columns": [{"name": "foo", "type": "STRING"}],
        }
        alert = self.create_alert(results)
        alert.options["selector"] = "min"
        self.assertEqual(alert.evaluate(), Alert.UNKNOWN_STATE)

    def test_evaluates_correctly_with_max_selector(self):
        results = {"rows": [{"foo": 1}, {"foo": 2}], "columns": [{"name": "foo", "type": "INTEGER"}]}
        alert = self.create_alert(results)
        alert.options["selector"] = "max"
        self.assertEqual(alert.evaluate(), Alert.OK_STATE)
        results = {
            "rows": [{"foo": "test"}, {"foo": "test"}, {"foo": "test"}],
            "columns": [{"name": "foo", "type": "STRING"}],
        }
        alert = self.create_alert(results)
        alert.options["selector"] = "max"
        self.assertEqual(alert.evaluate(), Alert.UNKNOWN_STATE)

    def test_evaluate_alerts_without_query_rel(self):
        query = self.factory.create_query(latest_query_data_id=None)
        alert = self.factory.create_alert(
            query_rel=query, options={"selector": "first", "op": "equals", "column": "foo", "value": "1"}
        )
        self.assertEqual(alert.evaluate(), Alert.UNKNOWN_STATE)

    def test_evaluate_return_unknown_when_value_is_none(self):
        alert = self.create_alert(get_results(None))
        self.assertEqual(alert.evaluate(), Alert.UNKNOWN_STATE)


class TestNextState(TestCase):
    def test_numeric_value(self):
        self.assertEqual(Alert.TRIGGERED_STATE, next_state(OPERATORS.get("=="), 1, "1"))
        self.assertEqual(Alert.TRIGGERED_STATE, next_state(OPERATORS.get("=="), 1, "1.0"))
        self.assertEqual(Alert.TRIGGERED_STATE, next_state(OPERATORS.get(">"), "5", 1))

    def test_numeric_value_and_plain_string(self):
        self.assertEqual(Alert.UNKNOWN_STATE, next_state(OPERATORS.get("=="), 1, "string"))

    def test_non_numeric_value(self):
        self.assertEqual(Alert.OK_STATE, next_state(OPERATORS.get("=="), "string", "1.0"))

    def test_string_value(self):
        self.assertEqual(Alert.TRIGGERED_STATE, next_state(OPERATORS.get("=="), "string", "string"))

    def test_boolean_value(self):
        self.assertEqual(Alert.TRIGGERED_STATE, next_state(OPERATORS.get("=="), False, "false"))
        self.assertEqual(Alert.TRIGGERED_STATE, next_state(OPERATORS.get("!="), False, "true"))


class TestAlertRenderTemplate(BaseTestCase):
    def create_alert(self, results, column="foo", value="5"):
        result = self.factory.create_query_result(data=results)
        query = self.factory.create_query(latest_query_data_id=result.id)
        alert = self.factory.create_alert(
            query_rel=query, options={"selector": "first", "op": "equals", "column": column, "value": value}
        )
        return alert

    def test_render_custom_alert_template(self):
        alert = self.create_alert(get_results(1))
        custom_alert = """
        <pre>
        ALERT_STATUS        {{ALERT_STATUS}}
        ALERT_SELECTOR      {{ALERT_SELECTOR}}
        ALERT_CONDITION     {{ALERT_CONDITION}}
        ALERT_THRESHOLD     {{ALERT_THRESHOLD}}
        ALERT_NAME          {{ALERT_NAME}}
        ALERT_URL           {{{ALERT_URL}}}
        QUERY_NAME          {{QUERY_NAME}}
        QUERY_URL           {{{QUERY_URL}}}
        QUERY_RESULT_VALUE  {{QUERY_RESULT_VALUE}}
        QUERY_RESULT_ROWS   {{{QUERY_RESULT_ROWS}}}
        QUERY_RESULT_COLS   {{{QUERY_RESULT_COLS}}}
        </pre>
        """
        expected = """
        <pre>
        ALERT_STATUS        UNKNOWN
        ALERT_SELECTOR      first
        ALERT_CONDITION     equals
        ALERT_THRESHOLD     5
        ALERT_NAME          %s
        ALERT_URL           %s/default/alerts/%d
        QUERY_NAME          Query
        QUERY_URL           %s/default/queries/%d
        QUERY_RESULT_VALUE  1
        QUERY_RESULT_ROWS   [{'foo': 1}]
        QUERY_RESULT_COLS   [{'name': 'foo', 'type': 'STRING'}]
        </pre>
        """ % (
            alert.name,
            settings.HOST,
            alert.id,
            settings.HOST,
            alert.query_id,
        )
        result = alert.render_template(textwrap.dedent(custom_alert))
        self.assertMultiLineEqual(result, textwrap.dedent(expected))

    def test_render_custom_alert_template_query_table(self):
        alert = self.create_alert(get_results(1))
        custom_alert = """
        <table>
        {{#QUERY_RESULT_TABLE}}
          <tr>
            {{#.}}
            <td>{{.}}</td>
            {{/.}}
          </tr>
        {{/QUERY_RESULT_TABLE}}
        </table>
        """
        expected = """
        <table>
          <tr>
            <td>1</td>
          </tr>
        </table>
        """
        result = alert.render_template(textwrap.dedent(custom_alert))
        self.assertMultiLineEqual(result, textwrap.dedent(expected))


class TestAlertCurrentValue(BaseTestCase):
    def create_alert(self, results, selector="first"):
        result = self.factory.create_query_result(data=results)
        query = self.factory.create_query(latest_query_data_id=result.id)
        return self.factory.create_alert(
            query_rel=query, options={"selector": selector, "op": ">", "column": "foo", "value": "1"}
        )

    def test_returns_first_row_value(self):
        alert = self.create_alert({"rows": [{"foo": 3}, {"foo": 7}], "columns": [{"name": "foo", "type": "INTEGER"}]})
        self.assertEqual(alert.current_value(), 3)

    def test_returns_aggregated_value_for_min_and_max_selectors(self):
        results = {"rows": [{"foo": "3"}, {"foo": 7}, {"foo": 1}], "columns": [{"name": "foo", "type": "INTEGER"}]}
        self.assertEqual(self.create_alert(results, selector="max").current_value(), 7.0)
        self.assertEqual(self.create_alert(results, selector="min").current_value(), 1.0)

    def test_returns_none_when_value_is_not_numeric(self):
        results = {"rows": [{"foo": "abc"}], "columns": [{"name": "foo", "type": "STRING"}]}
        self.assertIsNone(self.create_alert(results, selector="max").current_value())

    def test_returns_none_without_results(self):
        query = self.factory.create_query(latest_query_data_id=None)
        alert = self.factory.create_alert(query_rel=query, options={"column": "foo", "op": ">", "value": "1"})
        self.assertIsNone(alert.current_value())


class TestAlertStateChanges(BaseTestCase):
    def create_alert(self, value=5):
        result = self.factory.create_query_result(data=get_results(value))
        query = self.factory.create_query(latest_query_data_id=result.id)
        return self.factory.create_alert(
            query_rel=query, options={"selector": "first", "op": ">", "column": "foo", "value": "1"}
        )

    def test_record_state_change_stores_evaluated_value(self):
        alert = self.create_alert(value=5)

        change = alert.record_state_change(
            Alert.UNKNOWN_STATE, Alert.TRIGGERED_STATE, notified=True, trigger=AlertStateChange.SCHEDULED_TRIGGER
        )
        db.session.commit()

        self.assertEqual(
            change.to_dict(),
            {
                "id": change.id,
                "alert_id": alert.id,
                "previous_state": Alert.UNKNOWN_STATE,
                "new_state": Alert.TRIGGERED_STATE,
                "value": "5",
                "notified": True,
                "trigger": AlertStateChange.SCHEDULED_TRIGGER,
                "created_at": change.created_at,
            },
        )
        self.assertIsNotNone(change.created_at)

    def test_record_state_change_without_query_results(self):
        query = self.factory.create_query(latest_query_data_id=None)
        alert = self.factory.create_alert(query_rel=query, options={"column": "foo", "op": ">", "value": "1"})

        change = alert.record_state_change(
            Alert.TRIGGERED_STATE, Alert.UNKNOWN_STATE, notified=False, trigger=AlertStateChange.MANUAL_TRIGGER
        )

        self.assertIsNone(change.value)

    def test_record_state_change_reuses_given_value(self):
        alert = self.create_alert(value=5)

        with patch.object(Alert, "current_value") as current_value:
            change = alert.record_state_change(
                Alert.OK_STATE,
                Alert.TRIGGERED_STATE,
                notified=True,
                trigger=AlertStateChange.SCHEDULED_TRIGGER,
                value=7,
            )

        current_value.assert_not_called()
        self.assertEqual(change.value, "7")

    def test_evaluate_reuses_given_value(self):
        alert = self.create_alert(value=5)

        with patch.object(Alert, "current_value") as current_value:
            self.assertEqual(alert.evaluate(0), Alert.OK_STATE)
            self.assertEqual(alert.evaluate(None), Alert.UNKNOWN_STATE)

        current_value.assert_not_called()

    def test_for_alert_returns_most_recent_first(self):
        alert = self.create_alert()
        other_alert = self.create_alert()
        first = self.factory.create_alert_state_change(alert=alert)
        second = self.factory.create_alert_state_change(alert=alert)
        self.factory.create_alert_state_change(alert=other_alert)

        self.assertEqual([second.id, first.id], [c.id for c in AlertStateChange.for_alert(alert.id)])

    def test_record_state_change_prunes_old_entries(self):
        alert = self.create_alert()
        other_change = self.factory.create_alert_state_change()

        with patch.object(settings, "ALERT_STATE_HISTORY_LIMIT", 3):
            for _ in range(5):
                alert.record_state_change(
                    Alert.OK_STATE, Alert.TRIGGERED_STATE, notified=True, trigger=AlertStateChange.SCHEDULED_TRIGGER
                )
                db.session.commit()

        self.assertEqual(3, AlertStateChange.for_alert(alert.id).count())
        self.assertIsNotNone(AlertStateChange.query.get(other_change.id))

    def test_prune_is_disabled_with_zero_limit(self):
        alert = self.create_alert()
        for _ in range(3):
            self.factory.create_alert_state_change(alert=alert)

        self.assertEqual(0, AlertStateChange.prune(alert.id, 0))
        self.assertEqual(3, AlertStateChange.for_alert(alert.id).count())

    def test_deleting_alert_removes_its_history(self):
        change = self.factory.create_alert_state_change()
        change_id = change.id

        db.session.delete(change.alert)
        db.session.commit()
        db.session.expunge_all()

        self.assertIsNone(AlertStateChange.query.get(change_id))
