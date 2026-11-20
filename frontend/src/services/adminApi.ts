import axiosInstance from "./axiosInstance";

export type AdminUser = {
  id: number;
  first_name: string;
  last_name: string;
  email: string;
  active: boolean;
  role_names: string[];
};

export type AdminRole = { id: number; name: string };

export type PlantHolidayItem = {
  id: number;
  plant: string;
  holiday_date: string;
  name?: string | null;
};

export async function adminListUsers() {
  const res = await axiosInstance.get<AdminUser[]>("/admin/users");
  return res.data;
}

export async function adminCreateUser(payload: {
  first_name: string;
  last_name: string;
  email: string;
  password: string;
  active: boolean;
  role_names: string[];
}) {
  const res = await axiosInstance.post<AdminUser>("/admin/users", payload);
  return res.data;
}

export async function adminUpdateUser(
  userId: number,
  payload: Partial<{
    first_name: string;
    last_name: string;
    email: string;
    password: string;
    active: boolean;
    role_names: string[];
  }>,
) {
  const res = await axiosInstance.put<AdminUser>(`/admin/users/${userId}`, payload);
  return res.data;
}

export async function adminDeleteUser(userId: number) {
  const res = await axiosInstance.delete<{ message: string }>(`/admin/users/${userId}`);
  return res.data;
}

export async function adminListRoles() {
  const res = await axiosInstance.get<AdminRole[]>("/admin/roles");
  return res.data;
}

export async function adminCreateRole(payload: { name: string }) {
  const res = await axiosInstance.post<AdminRole>("/admin/roles", payload);
  return res.data;
}

export async function adminUpdateRole(roleId: number, payload: { name: string }) {
  const res = await axiosInstance.put<AdminRole>(`/admin/roles/${roleId}`, payload);
  return res.data;
}

export async function adminDeleteRole(roleId: number) {
  const res = await axiosInstance.delete<{ message: string; detached_users_count: number }>(
    `/admin/roles/${roleId}`,
  );
  return res.data;
}

export async function adminListPlantHolidays(plant?: string) {
  const params = plant ? { plant } : undefined;
  const res = await axiosInstance.get<{
    system_plants: string[];
    code_based_extras: Record<string, string[]>;
    items: PlantHolidayItem[];
  }>("/admin/plants/holidays", { params });
  return res.data;
}

export async function adminAddPlantHoliday(payload: {
  plant: string;
  holiday_date: string;
  name?: string;
}) {
  const res = await axiosInstance.post<PlantHolidayItem>("/admin/plants/holidays", payload);
  return res.data;
}

export async function adminDeletePlantHoliday(holidayId: number) {
  const res = await axiosInstance.delete<{ message: string }>(
    `/admin/plants/holidays/${holidayId}`,
  );
  return res.data;
}

export async function adminSchedulerStatus() {
  const res = await axiosInstance.get<{
    status: string;
    jobs: Array<{ id: string; name: string; next_run: string | null; trigger: string }>;
  }>("/admin/scheduler/status");
  return res.data;
}

export async function adminRunScheduler(daysBefore: number) {
  const res = await axiosInstance.post<{
    message: string;
    summary: Record<string, unknown>;
  }>("/admin/scheduler/run", { days_before: daysBefore });
  return res.data;
}
