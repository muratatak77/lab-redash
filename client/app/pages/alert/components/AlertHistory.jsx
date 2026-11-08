import { toUpper } from "lodash";
import React, { useCallback, useEffect, useState } from "react";
import PropTypes from "prop-types";

import Table from "antd/lib/table";
import TimeAgo from "@/components/TimeAgo";
import Tooltip from "@/components/Tooltip";
import AlertService from "@/services/alert";
import { STATE_CLASS } from "@/pages/alerts/AlertsList";

import "./AlertHistory.less";

const PAGE_SIZE = 10;

function StateLabel({ state }) {
  return <span className={`label ${STATE_CLASS[state] || "label-default"}`}>{toUpper(state)}</span>;
}

StateLabel.propTypes = {
  state: PropTypes.string.isRequired,
};

function NotificationStatus({ change }) {
  if (change.notified) {
    return (
      <span>
        <i className="fa fa-bell-o m-r-5" aria-hidden="true" />
        Sent
      </span>
    );
  }
  return (
    <Tooltip title="Notifications are skipped while an alert is muted, or when it is evaluated as OK for the first time.">
      <span className="text-muted">
        <i className="fa fa-bell-slash-o m-r-5" aria-hidden="true" />
        Not sent
      </span>
    </Tooltip>
  );
}

NotificationStatus.propTypes = {
  change: PropTypes.shape({ notified: PropTypes.bool }).isRequired,
};

const columns = [
  {
    title: "When",
    dataIndex: "created_at",
    render: (value) => <TimeAgo date={value} />,
  },
  {
    title: "State",
    key: "state",
    render: (text, change) => (
      <span className="alert-history-transition">
        <StateLabel state={change.previous_state} />
        <i className="fa fa-long-arrow-right" aria-hidden="true" />
        <span className="sr-only">changed to</span>
        <StateLabel state={change.new_state} />
      </span>
    ),
  },
  {
    title: "Value",
    dataIndex: "value",
    render: (value) => (value === null ? <span className="text-muted">n/a</span> : value),
  },
  {
    title: "Notification",
    key: "notified",
    render: (text, change) => <NotificationStatus change={change} />,
  },
  {
    title: "Evaluated",
    dataIndex: "trigger",
    render: (trigger) => (trigger === "manual" ? "Manually" : "On schedule"),
  },
];

export default function AlertHistory({ alertId, refreshKey }) {
  const [page, setPage] = useState(1);
  const [history, setHistory] = useState({ count: 0, results: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const load = useCallback(
    (pageToLoad) => {
      setLoading(true);
      return AlertService.history({ id: alertId }, { page: pageToLoad, page_size: PAGE_SIZE })
        .then((data) => {
          setHistory(data);
          setError(false);
        })
        .catch(() => setError(true))
        .finally(() => setLoading(false));
    },
    [alertId]
  );

  // Go back to the first page whenever the alert changes or was re-evaluated.
  useEffect(() => {
    setPage(1);
    load(1);
  }, [load, refreshKey]);

  const onPageChange = (newPage) => {
    setPage(newPage);
    load(newPage);
  };

  if (error) {
    return <div className="alert-history text-muted">Failed loading state history.</div>;
  }

  return (
    <div className="alert-history">
      <Table
        size="small"
        rowKey="id"
        columns={columns}
        dataSource={history.results}
        loading={loading}
        locale={{ emptyText: "This alert has not changed state yet." }}
        pagination={
          history.count > PAGE_SIZE
            ? { current: page, pageSize: PAGE_SIZE, total: history.count, onChange: onPageChange, simple: true }
            : false
        }
      />
    </div>
  );
}

AlertHistory.propTypes = {
  alertId: PropTypes.oneOfType([PropTypes.number, PropTypes.string]).isRequired,
  refreshKey: PropTypes.number,
};

AlertHistory.defaultProps = {
  refreshKey: 0,
};
