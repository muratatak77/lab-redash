import React from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import AlertService from "@/services/alert";
import AlertHistory from "./AlertHistory";

jest.mock("@/services/alert", () => ({ history: jest.fn() }));
// The alerts list page pulls in the whole visualizations library.
jest.mock("@/pages/alerts/AlertsList", () => ({
  STATE_CLASS: { unknown: "label-warning", ok: "label-success", triggered: "label-danger" },
}));

function change(id, previousState, newState, overrides = {}) {
  return {
    id,
    alert_id: 7,
    previous_state: previousState,
    new_state: newState,
    value: "12",
    notified: true,
    trigger: "scheduled",
    created_at: "1999-12-31T23:00:00.000Z",
    ...overrides,
  };
}

function rows() {
  return screen.getAllByRole("row").slice(1);
}

describe("AlertHistory", () => {
  afterEach(() => {
    AlertService.history.mockReset();
  });

  test("lists state changes", async () => {
    AlertService.history.mockResolvedValue({
      count: 2,
      page: 1,
      page_size: 10,
      results: [
        change(2, "triggered", "ok", { value: "3", notified: false, trigger: "manual" }),
        change(1, "unknown", "triggered", { value: null }),
      ],
    });

    render(<AlertHistory alertId={7} />);

    await waitFor(() => expect(rows()).toHaveLength(2));
    expect(AlertService.history).toHaveBeenCalledWith({ id: 7 }, { page: 1, page_size: 10 });

    const [recovered, triggered] = rows().map((row) => within(row));
    expect(recovered.getByText("TRIGGERED").className).toContain("label-danger");
    expect(recovered.getByText("OK").className).toContain("label-success");
    expect(recovered.getByText("3")).toBeTruthy();
    expect(recovered.getByText("Not sent")).toBeTruthy();
    expect(recovered.getByText("Manually")).toBeTruthy();

    expect(triggered.getByText("UNKNOWN").className).toContain("label-warning");
    expect(triggered.getByText("n/a")).toBeTruthy();
    expect(triggered.getByText("Sent")).toBeTruthy();
    expect(triggered.getByText("On schedule")).toBeTruthy();
  });

  test("shows a message when the alert never changed state", async () => {
    AlertService.history.mockResolvedValue({ count: 0, page: 1, page_size: 10, results: [] });

    render(<AlertHistory alertId={7} />);

    expect(await screen.findByText("This alert has not changed state yet.")).toBeTruthy();
  });

  test("loads other pages", async () => {
    AlertService.history.mockImplementation((alert, { page }) =>
      Promise.resolve({
        count: 12,
        page,
        page_size: 10,
        results: page === 1 ? [change(12, "ok", "triggered")] : [change(2, "unknown", "ok", { value: "1" })],
      })
    );

    render(<AlertHistory alertId={7} />);
    await screen.findByText("12");

    fireEvent.click(screen.getByTitle("Next Page"));

    await screen.findByText("1");
    expect(AlertService.history).toHaveBeenLastCalledWith({ id: 7 }, { page: 2, page_size: 10 });
  });

  test("reloads the first page when refreshKey changes", async () => {
    AlertService.history.mockResolvedValue({ count: 0, page: 1, page_size: 10, results: [] });

    const { rerender } = render(<AlertHistory alertId={7} refreshKey={0} />);
    await waitFor(() => expect(AlertService.history).toHaveBeenCalledTimes(1));

    rerender(<AlertHistory alertId={7} refreshKey={1} />);

    await waitFor(() => expect(AlertService.history).toHaveBeenCalledTimes(2));
    expect(AlertService.history).toHaveBeenLastCalledWith({ id: 7 }, { page: 1, page_size: 10 });
  });

  test("tells when the history could not be loaded", async () => {
    AlertService.history.mockRejectedValue(new Error("Forbidden"));

    render(<AlertHistory alertId={7} />);

    expect(await screen.findByText("Failed loading state history.")).toBeTruthy();
  });
});
