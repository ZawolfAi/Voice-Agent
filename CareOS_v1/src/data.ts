export type Patient = {
  name: string;
  id: string;
  age: number;
  gender: "Female" | "Male";
  condition: string;
  status: "Follow-up due" | "Stable" | "Needs attention";
  color: string;
  initials: string;
};

export type Appointment = {
  id?: string;
  startsAt?: string;
  date?: string;
  time: string;
  patientId: string;
  type:
    | "Follow-up consultation"
    | "Diabetes review"
    | "Cardiology referral"
    | "Medication review";
  status: "Confirmed" | "Arrived" | "Pending" | "Cancelled";
};

export const patients: Patient[] = [
  {
    name: "Mariam Hassan",
    id: "PT-2048",
    age: 42,
    gender: "Female",
    condition: "Hypertension",
    status: "Follow-up due",
    color: "#e6a27a",
    initials: "MH",
  },
  {
    name: "Omar Khaled",
    id: "PT-2047",
    age: 29,
    gender: "Male",
    condition: "Type 2 Diabetes",
    status: "Stable",
    color: "#8db4ad",
    initials: "OK",
  },
  {
    name: "Nour El Din",
    id: "PT-2043",
    age: 56,
    gender: "Male",
    condition: "Cardiac review",
    status: "Needs attention",
    color: "#c995a0",
    initials: "NE",
  },
  {
    name: "Salma Adel",
    id: "PT-2040",
    age: 35,
    gender: "Female",
    condition: "Migraine",
    status: "Stable",
    color: "#a6a3c5",
    initials: "SA",
  },
];

export const appointments: Appointment[] = [
  {
    time: "09:00",
    patientId: "PT-2048",
    type: "Follow-up consultation",
    status: "Confirmed",
  },
  {
    time: "10:30",
    patientId: "PT-2047",
    type: "Diabetes review",
    status: "Arrived",
  },
  {
    time: "12:00",
    patientId: "PT-2043",
    type: "Cardiology referral",
    status: "Pending",
  },
  {
    time: "14:30",
    patientId: "PT-2040",
    type: "Medication review",
    status: "Confirmed",
  },
];

export const getPatient = (patientId: string) =>
  patients.find((patient) => patient.id === patientId) ?? patients[0];
