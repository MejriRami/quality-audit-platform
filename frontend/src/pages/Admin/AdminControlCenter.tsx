import { useEffect, useMemo, useState } from "react";
import toast from "react-hot-toast";
import PageMeta from "../../components/common/PageMeta";
import PageBreadcrumb from "../../components/common/PageBreadCrumb";
import {
  AdminRole,
  AdminUser,
  adminCreateRole,
  adminCreateUser,
  adminDeleteRole,
  adminDeleteUser,
  adminListRoles,
  adminListUsers,
  adminRunScheduler,
  adminSchedulerStatus,
  adminUpdateRole,
  adminUpdateUser,
} from "../../services/adminApi";

type UserForm = {
  first_name: string;
  last_name: string;
  email: string;
  password: string;
  active: boolean;
  role_names: string[];
};

type ConfirmState = {
  open: boolean;
  title: string;
  message: string;
  confirmLabel: string;
  tone?: "danger" | "primary";
  onConfirm: null | (() => Promise<void>);
};

const initialUserForm: UserForm = {
  first_name: "",
  last_name: "",
  email: "",
  password: "",
  active: true,
  role_names: [],
};

const initialConfirmState: ConfirmState = {
  open: false,
  title: "",
  message: "",
  confirmLabel: "Confirm",
  tone: "primary",
  onConfirm: null,
};

const getApiErrorMessage = (err: any, fallback: string) => {
  const detail = err?.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0];
    if (typeof first === "string") return first;
    if (first?.msg) {
      const field = Array.isArray(first?.loc)
        ? first.loc.slice(1).join(".")
        : "";
      return field ? `${field}: ${first.msg}` : first.msg;
    }
    return fallback;
  }
  if (typeof err?.message === "string" && err.message.trim())
    return err.message;
  return fallback;
};

export default function AdminControlCenter() {
  const [loading, setLoading] = useState(false);
  const [savingUser, setSavingUser] = useState(false);
  const [savingRole, setSavingRole] = useState(false);
  const [confirming, setConfirming] = useState(false);

  const [users, setUsers] = useState<AdminUser[]>([]);
  const [roles, setRoles] = useState<AdminRole[]>([]);
  const [schedulerStatus, setSchedulerStatus] = useState<{
    status: string;
    jobs: Array<{
      id: string;
      name: string;
      next_run: string | null;
      trigger: string;
    }>;
  }>({ status: "unknown", jobs: [] });

  const [userForm, setUserForm] = useState<UserForm>(initialUserForm);
  const [editingUserId, setEditingUserId] = useState<number | null>(null);

  const [newRoleName, setNewRoleName] = useState("");
  const [editingRoleId, setEditingRoleId] = useState<number | null>(null);
  const [editingRoleName, setEditingRoleName] = useState("");

  const [confirmState, setConfirmState] =
    useState<ConfirmState>(initialConfirmState);

  const roleOptions = useMemo(() => roles.map((r) => r.name), [roles]);

  const closeConfirm = () => setConfirmState(initialConfirmState);

  const openConfirm = (payload: Omit<ConfirmState, "open">) => {
    setConfirmState({ ...payload, open: true });
  };

  const loadAll = async () => {
    setLoading(true);
    try {
      const [u, r, s] = await Promise.all([
        adminListUsers(),
        adminListRoles(),
        adminSchedulerStatus(),
      ]);
      setUsers(u);
      setRoles(r);
      setSchedulerStatus(s);
    } catch (err: any) {
      toast.error(getApiErrorMessage(err, "Failed to load admin data"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadAll();
  }, []);

  const onCreateRole = async (e: React.FormEvent) => {
    e.preventDefault();
    const name = newRoleName.trim();
    if (!name) {
      toast.error("Role name is required");
      return;
    }
    setSavingRole(true);
    try {
      const created = await adminCreateRole({ name });
      toast.success(`Role '${created.name}' created`);
      setNewRoleName("");
      await loadAll();
    } catch (err: any) {
      toast.error(getApiErrorMessage(err, "Role creation failed"));
    } finally {
      setSavingRole(false);
    }
  };

  const onUpdateRole = async (e: React.FormEvent) => {
    e.preventDefault();
    if (editingRoleId == null) return;

    const name = editingRoleName.trim();
    if (!name) {
      toast.error("Role name is required");
      return;
    }

    setSavingRole(true);
    try {
      const updated = await adminUpdateRole(editingRoleId, { name });
      toast.success(`Role updated to '${updated.name}'`);
      setEditingRoleId(null);
      setEditingRoleName("");
      await loadAll();
    } catch (err: any) {
      toast.error(getApiErrorMessage(err, "Role update failed"));
    } finally {
      setSavingRole(false);
    }
  };

  const startEditRole = (role: AdminRole) => {
    setEditingRoleId(role.id);
    setEditingRoleName(role.name);
  };

  const onSubmitUser = async (e: React.FormEvent) => {
    e.preventDefault();

    if (
      !userForm.first_name.trim() ||
      !userForm.last_name.trim() ||
      !userForm.email.trim()
    ) {
      toast.error("First name, last name, and email are required");
      return;
    }

    if (editingUserId == null) {
      if (!userForm.password.trim()) {
        toast.error("Password is required for new users");
        return;
      }
      if (userForm.password.trim().length < 8) {
        toast.error("Password must be at least 8 characters");
        return;
      }
      if (!userForm.role_names.length) {
        toast.error("At least one role is required for new users");
        return;
      }
    }

    setSavingUser(true);
    try {
      if (editingUserId == null) {
        await adminCreateUser({
          first_name: userForm.first_name.trim(),
          last_name: userForm.last_name.trim(),
          email: userForm.email.trim(),
          password: userForm.password,
          active: userForm.active,
          role_names: userForm.role_names,
        });
        toast.success("User created");
      } else {
        const payload: {
          first_name: string;
          last_name: string;
          email: string;
          active: boolean;
          role_names: string[];
          password?: string;
        } = {
          first_name: userForm.first_name.trim(),
          last_name: userForm.last_name.trim(),
          email: userForm.email.trim(),
          active: userForm.active,
          role_names: userForm.role_names,
        };

        if (userForm.password.trim()) {
          if (userForm.password.trim().length < 8) {
            toast.error("Password must be at least 8 characters");
            setSavingUser(false);
            return;
          }
          payload.password = userForm.password;
        }

        await adminUpdateUser(editingUserId, payload);
        toast.success("User updated");
      }
      setUserForm(initialUserForm);
      setEditingUserId(null);
      await loadAll();
    } catch (err: any) {
      toast.error(getApiErrorMessage(err, "User save failed"));
    } finally {
      setSavingUser(false);
    }
  };

  const startEditUser = (user: AdminUser) => {
    setEditingUserId(user.id);
    setUserForm({
      first_name: user.first_name,
      last_name: user.last_name,
      email: user.email,
      password: "",
      active: user.active,
      role_names: user.role_names,
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
    toast.success("Editing user details");
  };

  const requestDeleteUser = (user: AdminUser) => {
    openConfirm({
      title: "Delete User",
      message: `Delete '${user.first_name} ${user.last_name}'? If linked records exist, user will be deactivated automatically.`,
      confirmLabel: "Delete User",
      tone: "danger",
      onConfirm: async () => {
        const res = await adminDeleteUser(user.id);
        toast.success(res.message || "User operation completed");
        await loadAll();
      },
    });
  };

  const requestDeleteRole = (role: AdminRole) => {
    openConfirm({
      title: "Delete Role",
      message: `Delete role '${role.name}'? Assigned users will be detached from this role.`,
      confirmLabel: "Delete Role",
      tone: "danger",
      onConfirm: async () => {
        const res = await adminDeleteRole(role.id);
        toast.success(
          res.detached_users_count > 0
            ? `${res.message} Detached from ${res.detached_users_count} user(s).`
            : res.message,
        );
        if (editingRoleId === role.id) {
          setEditingRoleId(null);
          setEditingRoleName("");
        }
        await loadAll();
      },
    });
  };

  const runReminder = async (daysBefore: number) => {
    try {
      const res = await adminRunScheduler(daysBefore);
      toast.success(res.message);
      await loadAll();
    } catch (err: any) {
      toast.error(getApiErrorMessage(err, "Manual run failed"));
    }
  };

  const onConfirmDialog = async () => {
    if (!confirmState.onConfirm) {
      closeConfirm();
      return;
    }

    setConfirming(true);
    try {
      await confirmState.onConfirm();
      closeConfirm();
    } catch (err: any) {
      toast.error(getApiErrorMessage(err, "Operation failed"));
    } finally {
      setConfirming(false);
    }
  };

  return (
    <>
      <PageMeta
        title="Admin Control Center"
        description="Manage platform users, role governance, and scheduler controls."
      />
      <div className="space-y-6">
        <PageBreadcrumb
          kicker="Administration"
          pageTitle="Admin Control Center"
          description="Manage platform users, role governance, and operational scheduler controls."
        />

        <section className="grid gap-6 xl:grid-cols-3">
          <div className="rounded-2xl border border-slate-200/70 bg-white p-5 shadow-sm dark:border-slate-800/70 dark:bg-slate-900/60 xl:col-span-2">
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white">
              {editingUserId ? "Update User" : "Create User"}
            </h2>
            <form className="mt-4 space-y-3" onSubmit={onSubmitUser}>
              <div className="grid grid-cols-2 gap-3">
                <input
                  className="rounded-lg border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
                  placeholder="First name"
                  value={userForm.first_name}
                  onChange={(e) =>
                    setUserForm((p) => ({ ...p, first_name: e.target.value }))
                  }
                  required
                />
                <input
                  className="rounded-lg border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
                  placeholder="Last name"
                  value={userForm.last_name}
                  onChange={(e) =>
                    setUserForm((p) => ({ ...p, last_name: e.target.value }))
                  }
                  required
                />
              </div>
              <input
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
                placeholder="user841@example.com"
                value={userForm.email}
                onChange={(e) =>
                  setUserForm((p) => ({ ...p, email: e.target.value }))
                }
                required
              />
              <input
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
                placeholder={
                  editingUserId ? "New password (optional)" : "Password"
                }
                type="password"
                minLength={editingUserId ? undefined : 8}
                value={userForm.password}
                onChange={(e) =>
                  setUserForm((p) => ({ ...p, password: e.target.value }))
                }
              />
              <div className="rounded-lg border border-slate-200 p-3 dark:border-slate-700">
                <p className="mb-2 text-xs font-semibold uppercase text-slate-500 dark:text-slate-400">
                  Roles
                </p>
                <div className="flex flex-wrap gap-3">
                  {roleOptions.map((role) => (
                    <label
                      key={role}
                      className="inline-flex items-center gap-2 text-sm text-slate-600 dark:text-slate-200"
                    >
                      <input
                        type="checkbox"
                        checked={userForm.role_names.includes(role)}
                        onChange={(e) =>
                          setUserForm((p) => ({
                            ...p,
                            role_names: e.target.checked
                              ? [...p.role_names, role]
                              : p.role_names.filter((r) => r !== role),
                          }))
                        }
                      />
                      {role}
                    </label>
                  ))}
                </div>
              </div>
              <label className="inline-flex items-center gap-2 text-sm text-[#3f7090] dark:text-[#cfe9f9]">
                <input
                  type="checkbox"
                  checked={userForm.active}
                  onChange={(e) =>
                    setUserForm((p) => ({ ...p, active: e.target.checked }))
                  }
                />
                Active
              </label>
              <div className="flex gap-2">
                <button
                  type="submit"
                  disabled={savingUser}
                  className="rounded-lg bg-[#064273] dark:bg-[#0a5f95] px-4 py-2 text-sm font-semibold text-white hover:bg-[#0a5f95] dark:hover:bg-[#0d74b5] disabled:opacity-60"
                >
                  {savingUser
                    ? "Saving..."
                    : editingUserId
                      ? "Update User"
                      : "Create User"}
                </button>
                {editingUserId != null && (
                  <button
                    type="button"
                    className="rounded-lg border border-[#9ec6df] dark:border-[#0f6ea9] px-4 py-2 text-sm"
                    onClick={() => {
                      setEditingUserId(null);
                      setUserForm(initialUserForm);
                    }}
                  >
                    Cancel
                  </button>
                )}
              </div>
            </form>
          </div>

          <div className="rounded-2xl border border-[#b8d3e6] bg-white/95 dark:border-[#0a5f95] dark:bg-[#072f4a]/80 p-5 shadow-sm">
            <h2 className="text-lg font-semibold text-[#064273] dark:text-[#e1f2ff]">
              Role Management
            </h2>
            <p className="mt-1 text-sm text-[#3f7090] dark:text-[#cfe9f9]">
              Create, edit, and delete roles.
            </p>

            <form className="mt-4 space-y-3" onSubmit={onCreateRole}>
              <input
                className="w-full rounded-lg border border-[#9ec6df] dark:border-[#0f6ea9] px-3 py-2 text-sm"
                placeholder="Role name"
                value={newRoleName}
                onChange={(e) => setNewRoleName(e.target.value)}
                required
              />
              <button
                type="submit"
                disabled={savingRole}
                className="rounded-lg bg-[#064273] dark:bg-[#0a5f95] px-4 py-2 text-sm font-semibold text-white hover:bg-[#0a5f95] dark:hover:bg-[#0d74b5] disabled:opacity-60"
              >
                {savingRole ? "Saving..." : "Add Role"}
              </button>
            </form>

            <div className="mt-4 rounded-lg border border-slate-200 p-3">
              <p className="mb-2 text-xs font-semibold uppercase text-[#5f89a3] dark:text-[#b8dcf2]">
                Existing Roles
              </p>
              <div className="max-h-64 space-y-2 overflow-auto">
                {roles.map((role) => (
                  <div
                    key={role.id}
                    className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2"
                  >
                    <span className="text-sm text-[#064273] dark:text-[#e1f2ff]">
                      {role.name}
                    </span>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        className="rounded-md border border-[#9ec6df] dark:border-[#0f6ea9] px-2 py-1 text-xs"
                        onClick={() => startEditRole(role)}
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        className="rounded-md border border-rose-300 px-2 py-1 text-xs text-rose-700"
                        onClick={() => requestDeleteRole(role)}
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                ))}
                {!roles.length && (
                  <p className="text-xs text-[#5f89a3] dark:text-[#b8dcf2]">
                    No roles found
                  </p>
                )}
              </div>
            </div>

            {editingRoleId != null && (
              <form
                className="mt-4 space-y-2 rounded-lg border border-slate-200 p-3"
                onSubmit={onUpdateRole}
              >
                <p className="text-xs font-semibold uppercase text-[#5f89a3] dark:text-[#b8dcf2]">
                  Edit Role
                </p>
                <input
                  className="w-full rounded-lg border border-[#9ec6df] dark:border-[#0f6ea9] px-3 py-2 text-sm"
                  value={editingRoleName}
                  onChange={(e) => setEditingRoleName(e.target.value)}
                  required
                />
                <div className="flex gap-2">
                  <button
                    type="submit"
                    disabled={savingRole}
                    className="rounded-md bg-[#064273] dark:bg-[#0a5f95] px-3 py-1 text-xs font-semibold text-white hover:bg-[#0a5f95] dark:hover:bg-[#0d74b5] disabled:opacity-60"
                  >
                    Update
                  </button>
                  <button
                    type="button"
                    className="rounded-md border border-[#9ec6df] dark:border-[#0f6ea9] px-3 py-1 text-xs"
                    onClick={() => {
                      setEditingRoleId(null);
                      setEditingRoleName("");
                    }}
                  >
                    Cancel
                  </button>
                </div>
              </form>
            )}
          </div>
        </section>

        <section className="rounded-2xl border border-[#b8d3e6] bg-white/95 dark:border-[#0a5f95] dark:bg-[#072f4a]/80 p-5 shadow-sm">
          <h2 className="text-lg font-semibold text-[#064273] dark:text-[#e1f2ff]">
            Users
          </h2>
          <div className="mt-4 overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="text-left text-[#5f89a3] dark:text-[#b8dcf2]">
                  <th className="py-2">Name</th>
                  <th className="py-2">Email</th>
                  <th className="py-2">Roles</th>
                  <th className="py-2">Status</th>
                  <th className="py-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr
                    key={u.id}
                    className="border-t border-slate-100 text-[#3f7090] dark:text-[#cfe9f9]"
                  >
                    <td className="py-2">
                      {u.first_name} {u.last_name}
                    </td>
                    <td className="py-2">{u.email}</td>
                    <td className="py-2">
                      {u.role_names.join(", ") || "none"}
                    </td>
                    <td className="py-2">{u.active ? "Active" : "Inactive"}</td>
                    <td className="py-2">
                      <div className="flex gap-2">
                        <button
                          type="button"
                          className="rounded-md border border-[#9ec6df] dark:border-[#0f6ea9] px-2 py-1 text-xs"
                          onClick={() => startEditUser(u)}
                        >
                          Edit
                        </button>
                        <button
                          type="button"
                          className="rounded-md border border-rose-300 px-2 py-1 text-xs text-rose-700"
                          onClick={() => requestDeleteUser(u)}
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {loading && (
              <p className="mt-3 text-sm text-[#5f89a3] dark:text-[#b8dcf2]">
                Loading...
              </p>
            )}
          </div>
        </section>

        <section className="rounded-2xl border border-[#b8d3e6] bg-white/95 dark:border-[#0a5f95] dark:bg-[#072f4a]/80 p-5 shadow-sm">
          <h2 className="text-lg font-semibold text-[#064273] dark:text-[#e1f2ff]">
            Scheduler Control
          </h2>
          <p className="mt-1 text-sm text-[#3f7090] dark:text-[#cfe9f9]">
            Status: {schedulerStatus.status}
          </p>
          <div className="mt-4 flex gap-2">
            <button
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700"
              onClick={() => runReminder(2)}
            >
              Run D-2 Reminders
            </button>
            <button
              className="rounded-lg bg-amber-600 px-4 py-2 text-sm font-semibold text-white hover:bg-amber-700"
              onClick={() => runReminder(1)}
            >
              Run D-1 Reminders
            </button>
          </div>
          <div className="mt-4 overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="text-left text-[#5f89a3] dark:text-[#b8dcf2]">
                  <th className="py-2">Job</th>
                  <th className="py-2">Next Run</th>
                  <th className="py-2">Trigger</th>
                </tr>
              </thead>
              <tbody>
                {schedulerStatus.jobs.map((job) => (
                  <tr
                    key={job.id}
                    className="border-t border-slate-100 text-[#3f7090] dark:text-[#cfe9f9]"
                  >
                    <td className="py-2">{job.name}</td>
                    <td className="py-2">{job.next_run ?? "N/A"}</td>
                    <td className="py-2">{job.trigger}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      {confirmState.open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/45 p-4">
          <div className="w-full max-w-md rounded-2xl border border-[#b8d3e6] bg-white/95 dark:border-[#0a5f95] dark:bg-[#072f4a]/80 p-5 shadow-2xl">
            <h3 className="text-lg font-semibold text-[#064273] dark:text-[#e1f2ff]">
              {confirmState.title}
            </h3>
            <p className="mt-2 text-sm text-[#3f7090] dark:text-[#cfe9f9]">
              {confirmState.message}
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                className="rounded-lg border border-[#9ec6df] dark:border-[#0f6ea9] px-4 py-2 text-sm"
                onClick={closeConfirm}
                disabled={confirming}
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={confirming}
                onClick={onConfirmDialog}
                className={`rounded-lg px-4 py-2 text-sm font-semibold text-white disabled:opacity-60 ${
                  confirmState.tone === "danger"
                    ? "bg-rose-600 hover:bg-rose-700"
                    : "bg-[#064273] dark:bg-[#0a5f95] hover:bg-[#0a5f95] dark:hover:bg-[#0d74b5]"
                }`}
              >
                {confirming ? "Please wait..." : confirmState.confirmLabel}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
