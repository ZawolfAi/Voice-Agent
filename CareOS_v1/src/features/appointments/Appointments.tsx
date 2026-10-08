import { useEffect, useState } from "react";
import {
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Check,
  Plus,
  X,
} from "lucide-react";
import {
  createAppointment,
  getAppointments,
  rescheduleAppointment,
  updateAppointmentStatus,
} from "../../api/appointments";
import { getPatients } from "../../api/patients";
import { type Appointment } from "../../data";
import { PageHeading } from "../../components/PageHeading";
import type { Language, TranslationKey } from "../../i18n";

type Translator = (key: TranslationKey) => string;

function localDateKey(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function AppointmentModal({ close, t }: { close: () => void; t: Translator }) {
  const [people, setPeople] = useState<Array<{ id: string; label: string }>>(
    [],
  );
  const [patientId, setPatientId] = useState("");
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [time, setTime] = useState("15:30");
  const [reason, setReason] = useState("Follow-up consultation");
  useEffect(() => {
    getPatients()
      .then((items) => {
        const next = items.map((item) => ({
          id: item.id,
          label: `${item.given_name} ${item.family_name} · ${item.patient_code}`,
        }));
        setPeople(next);
        setPatientId(next[0]?.id ?? "");
      })
      .catch(() => undefined);
  }, []);
  return (
    <div className="modal-backdrop" onClick={close}>
      <div className="modal" onClick={(event) => event.stopPropagation()}>
        <div className="modal-heading">
          <div>
            <div className="eyebrow">{t("schedule")}</div>
            <h2>{t("newAppointment")}</h2>
          </div>
          <button className="icon-btn" onClick={close}>
            <X size={18} />
          </button>
        </div>
        <label>
          {t("patient")}
          <select
            value={patientId}
            onChange={(event) => setPatientId(event.target.value)}
          >
            {people.length ? (
              people.map((person) => (
                <option key={person.id} value={person.id}>
                  {person.label}
                </option>
              ))
            ) : (
              <option>API patient required</option>
            )}
          </select>
        </label>
        <div className="form-row">
          <label>
            {t("date")}
            <input
              type="date"
              value={date}
              onChange={(event) => setDate(event.target.value)}
            />
          </label>
          <label>
            {t("time")}
            <input
              type="time"
              value={time}
              onChange={(event) => setTime(event.target.value)}
            />
          </label>
        </div>
        <label>
          {t("appointmentType")}
          <select
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          >
            <option>Follow-up consultation</option>
            <option>Medication review</option>
          </select>
        </label>
        <button
          className="primary-btn full-width"
          disabled={!patientId}
          onClick={async () => {
            try {
              await createAppointment({
                patient_id: patientId,
                starts_at: new Date(`${date}T${time}:00`).toISOString(),
                reason,
                status: "confirmed",
              });
              close();
              window.dispatchEvent(
                new CustomEvent("careos:toast", {
                  detail: t("appointmentSaved"),
                }),
              );
            } catch (error) {
              window.dispatchEvent(
                new CustomEvent("careos:toast", {
                  detail:
                    error instanceof Error
                      ? error.message
                      : t("appointmentSaveFailed"),
                }),
              );
            }
          }}
        >
          <Check size={16} /> {t("confirmAppointment")}
        </button>
      </div>
    </div>
  );
}

function RescheduleModal({
  appointment,
  close,
  reload,
}: {
  appointment: Appointment;
  close: () => void;
  reload: () => Promise<void>;
}) {
  const [date, setDate] = useState(
    new Date(appointment.startsAt || Date.now()).toISOString().slice(0, 10),
  );
  const [time, setTime] = useState(
    new Date(appointment.startsAt || Date.now()).toISOString().slice(11, 16),
  );
  const [saving, setSaving] = useState(false);
  const save = async () => {
    if (!appointment.id) return;
    setSaving(true);
    try {
      await rescheduleAppointment(
        appointment.id,
        new Date(`${date}T${time}:00`).toISOString(),
      );
      close();
      await reload();
    } catch (error) {
      window.dispatchEvent(
        new CustomEvent("careos:toast", {
          detail:
            error instanceof Error
              ? error.message
              : "Could not reschedule appointment",
        }),
      );
    } finally {
      setSaving(false);
    }
  };
  return (
    <div className="modal-backdrop" onClick={close}>
      <div className="modal" onClick={(event) => event.stopPropagation()}>
        <div className="modal-heading">
          <div>
            <div className="eyebrow">Schedule</div>
            <h2>Reschedule appointment</h2>
          </div>
          <button className="icon-btn" onClick={close}>
            <X size={18} />
          </button>
        </div>
        <div className="form-row">
          <label>
            Date
            <input
              type="date"
              value={date}
              onChange={(event) => setDate(event.target.value)}
            />
          </label>
          <label>
            Time
            <input
              type="time"
              value={time}
              onChange={(event) => setTime(event.target.value)}
            />
          </label>
        </div>
        <button
          className="primary-btn full-width"
          disabled={saving}
          onClick={() => void save()}
        >
          {saving ? "Saving..." : "Save new time"}
        </button>
      </div>
    </div>
  );
}

export function Appointments({
  t,
  language,
}: {
  t: Translator;
  language: Language;
}) {
  const [showForm, setShowForm] = useState(false);
  const [rescheduling, setRescheduling] = useState<Appointment | null>(null);
  const [filter, setFilter] = useState<Appointment["status"] | "All">("All");
  const [dayOffset, setDayOffset] = useState(0);
  const [showCalendar, setShowCalendar] = useState(false);
  const [calendarAnchor, setCalendarAnchor] = useState(() => new Date());
  const [live, setLive] = useState<Appointment[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const load = () => {
    setLoading(true);
    return Promise.all([getAppointments({ pageSize: 100 }), getPatients()])
      .then(([records, people]) => {
        const ids = new Map(
          people.map((person) => [person.id, person.patient_code]),
        );
        setLive(
          records.map((item) => ({
            id: item.id,
            startsAt: item.starts_at,
            date: new Date(item.starts_at).toDateString(),
            time: new Date(item.starts_at).toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
              hour12: false,
            }),
            patientId: ids.get(item.patient_id) || item.patient_id,
            type: item.reason as Appointment["type"],
            status: ({
              confirmed: "Confirmed",
              arrived: "Arrived",
              pending: "Pending",
              cancelled: "Cancelled",
            }[item.status] || "Pending") as Appointment["status"],
          })),
        );
        setLoadError(null);
      })
      .catch((reason: unknown) => {
        setLive([]);
        setLoadError(
          reason instanceof Error
            ? reason.message
            : "Could not load appointments.",
        );
      })
      .finally(() => setLoading(false));
  };
  useEffect(() => {
    void load();
  }, []);
  const rangeStart = new Date();
  rangeStart.setHours(0, 0, 0, 0);
  rangeStart.setDate(rangeStart.getDate() + dayOffset);
  const rangeEnd = new Date(rangeStart);
  rangeEnd.setDate(rangeEnd.getDate() + 1);
  const locale = language === "ar" ? "ar-EG" : "en-US";
  const rangeLabel = rangeStart.toLocaleDateString(locale, {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
  const list = live;
  const rangeAppointments = list.filter((item) => {
    const appointmentDate = new Date(item.startsAt || item.date || "");
    const timestamp = appointmentDate.getTime();
    return timestamp >= rangeStart.getTime() && timestamp < rangeEnd.getTime();
  });
  const visible =
    filter === "All"
      ? rangeAppointments
      : rangeAppointments.filter((item) => item.status === filter);
  const calendarMonthStart = new Date(
    calendarAnchor.getFullYear(),
    calendarAnchor.getMonth(),
    1,
  );
  const calendarGridStart = new Date(calendarMonthStart);
  calendarGridStart.setDate(
    calendarGridStart.getDate() - ((calendarGridStart.getDay() + 6) % 7),
  );
  const calendarDays = Array.from({ length: 42 }, (_, index) => {
    const date = new Date(calendarGridStart);
    date.setDate(calendarGridStart.getDate() + index);
    const appointmentCount = live.filter((item) =>
      item.startsAt
        ? localDateKey(new Date(item.startsAt)) === localDateKey(date)
        : false,
    ).length;
    return { date, appointmentCount };
  });
  const weekdayLabels = Array.from({ length: 7 }, (_, index) => {
    const monday = new Date(2024, 0, 1 + index);
    return monday.toLocaleDateString(locale, { weekday: "short" });
  });
  const changeCalendarMonth = (offset: number) => {
    setCalendarAnchor((current) => {
      const next = new Date(current);
      next.setDate(1);
      next.setMonth(next.getMonth() + offset);
      return next;
    });
  };
  const selectCalendarDate = (selectedDate: Date) => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const selected = new Date(selectedDate);
    selected.setHours(0, 0, 0, 0);
    setDayOffset(Math.round((selected.getTime() - today.getTime()) / 86400000));
    setShowCalendar(false);
  };
  return (
    <>
      <PageHeading
        eyebrow={t("schedule")}
        title={t("appointments")}
        detail={t("scheduleDetail")}
        action={
          <button className="primary-btn" onClick={() => setShowForm(true)}>
            <Plus size={17} /> {t("newAppointment")}
          </button>
        }
      />
      <div className="calendar-bar">
        <button
          type="button"
          className={`outline-btn calendar-view-button ${showCalendar ? "active" : ""}`}
          aria-expanded={showCalendar}
          aria-controls="appointments-calendar"
          onClick={() => {
            if (!showCalendar) setCalendarAnchor(new Date(rangeStart));
            setShowCalendar((current) => !current);
          }}
        >
          <CalendarDays size={15} />
          {showCalendar ? t("hideCalendar") : t("calendarView")}
        </button>
        <button
          className="round-btn"
          aria-label={t("previousDay")}
          onClick={() => setDayOffset((value) => value - 1)}
        >
          <ChevronLeft size={16} />
        </button>
        <div>
          <strong>{rangeLabel}</strong>
          <span>
            {rangeAppointments.length} {t("appointmentsCountLabel")}
          </span>
        </div>
        <button
          className="round-btn"
          aria-label={t("nextDay")}
          onClick={() => setDayOffset((value) => value + 1)}
        >
          <ChevronRight size={16} />
        </button>
        <select
          className="filter-btn"
          value={filter}
          onChange={(event) =>
            setFilter(event.target.value as Appointment["status"] | "All")
          }
        >
          <option value="All">{t("allStatuses")}</option>
          <option value="Confirmed">{t("confirmed")}</option>
          <option value="Pending">{t("pending")}</option>
          <option value="Arrived">{t("arrived")}</option>
        </select>
      </div>
      {showCalendar && (
        <section
          className="calendar-month-view"
          id="appointments-calendar"
          aria-label={t("calendarView")}
        >
          <div className="calendar-month-heading">
            <button
              type="button"
              className="round-btn"
              aria-label={t("previousMonth")}
              onClick={() => changeCalendarMonth(-1)}
            >
              <ChevronLeft size={16} />
            </button>
            <h2>
              {calendarMonthStart.toLocaleDateString(locale, {
                month: "long",
                year: "numeric",
              })}
            </h2>
            <button
              type="button"
              className="round-btn"
              aria-label={t("nextMonth")}
              onClick={() => changeCalendarMonth(1)}
            >
              <ChevronRight size={16} />
            </button>
          </div>
          <div className="calendar-weekdays" aria-hidden="true">
            {weekdayLabels.map((weekday, index) => (
              <span key={`${weekday}-${index}`}>{weekday}</span>
            ))}
          </div>
          <div className="calendar-days">
            {calendarDays.map(({ date, appointmentCount }) => {
              const isSelected =
                localDateKey(date) === localDateKey(rangeStart);
              const isToday = localDateKey(date) === localDateKey(new Date());
              return (
                <button
                  type="button"
                  key={localDateKey(date)}
                  className={[
                    date.getMonth() === calendarMonthStart.getMonth()
                      ? ""
                      : "outside-month",
                    isSelected ? "selected" : "",
                    isToday ? "today" : "",
                  ]
                    .filter(Boolean)
                    .join(" ")}
                  data-date={localDateKey(date)}
                  aria-label={`${date.toLocaleDateString(locale, { weekday: "long", day: "numeric", month: "long", year: "numeric" })}${appointmentCount ? `, ${appointmentCount} ${t("appointmentsCountLabel")}` : ""}`}
                  aria-pressed={isSelected}
                  onClick={() => selectCalendarDate(date)}
                >
                  <span>
                    {date.toLocaleDateString(locale, { day: "numeric" })}
                  </span>
                  {appointmentCount > 0 && (
                    <span className="calendar-day-count">
                      {appointmentCount}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </section>
      )}
      <section className="panel schedule-panel">
        {loading && (
          <div className="loading-state">{t("loadingAppointments")}</div>
        )}
        {!loading && loadError && (
          <div className="error-state" role="alert">
            {loadError}
          </div>
        )}
        {!loading &&
          !loadError &&
          visible.map((item) => (
            <div
              className="appointment-row"
              key={`${item.id || item.time}-${item.patientId}`}
            >
              <div>
                <strong>{item.time}</strong>
                <span>{item.patientId}</span>
              </div>
              <span>{item.type}</span>
              <span
                className={`status ${item.status === "Confirmed" ? "confirmed" : "pending"}`}
              >
                {item.status}
              </span>
              {item.status !== "Cancelled" && (
                <button
                  className="text-btn"
                  onClick={() => setRescheduling(item)}
                >
                  Reschedule
                </button>
              )}
              <button
                className="text-btn"
                onClick={async () => {
                  if (!item.id) return;
                  try {
                    await updateAppointmentStatus(
                      item.id,
                      item.status === "Confirmed" ? "cancelled" : "confirmed",
                    );
                    await load();
                  } catch (error) {
                    window.dispatchEvent(
                      new CustomEvent("careos:toast", {
                        detail:
                          error instanceof Error
                            ? error.message
                            : t("appointmentSaveFailed"),
                      }),
                    );
                  }
                }}
              >
                {item.status === "Confirmed" ? "Cancel" : t("updateStatus")}
              </button>
            </div>
          ))}
        {!loading && !loadError && visible.length === 0 && (
          <div className="empty-state">{t("noAppointments")}</div>
        )}
      </section>
      {showForm && (
        <AppointmentModal
          close={() => {
            setShowForm(false);
            void load();
          }}
          t={t}
        />
      )}
      {rescheduling && (
        <RescheduleModal
          appointment={rescheduling}
          close={() => setRescheduling(null)}
          reload={load}
        />
      )}
    </>
  );
}
