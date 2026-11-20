import { useState, type FormEvent } from "react";
import { LogOut, ShieldCheck } from "lucide-react";
import logoNorthwindWide from "../../assets/logo/logo-northwind.png";
import {
  apiErrorMessage,
  clearPortalSession,
  loadPortalSession,
  requestPortalCode,
  savePortalSession,
  setPortalSessionToken,
  verifyPortalCode,
  type PortalSession,
} from "../../services/externalCertificationsApi";
import ExternalCertifications from "./ExternalCertifications";
import { inputClass } from "./CertificationFormModal";

// Public entry to External Certifications, like the auditee portal: no app
// account, the visitor proves their @northwind.com mailbox with a code.
function initialSession(): PortalSession | null {
  const session = loadPortalSession();
  setPortalSessionToken(session?.session_token ?? null);
  return session;
}

const primaryButton =
  "w-full rounded-xl bg-gradient-to-r from-[#064273] to-[#0a5f95] px-4 py-2.5 text-sm font-semibold text-white transition hover:from-[#05375f] hover:to-[#084d79] disabled:opacity-60";

export default function CertificationsPortal() {
  const [session, setSession] = useState<PortalSession | null>(initialSession);
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [codeSent, setCodeSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleRequestCode(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await requestPortalCode(email);
      setCodeSent(true);
    } catch (err) {
      setError(apiErrorMessage(err, "Could not send the code."));
    } finally {
      setBusy(false);
    }
  }

  async function handleVerify(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const next = await verifyPortalCode(email, code);
      savePortalSession(next);
      setPortalSessionToken(next.session_token);
      setSession(next);
    } catch (err) {
      setError(apiErrorMessage(err, "Invalid code."));
    } finally {
      setBusy(false);
    }
  }

  function signOut() {
    clearPortalSession();
    setSession(null);
    setCode("");
    setCodeSent(false);
  }

  if (session) {
    return (
      <div className="min-h-screen bg-[#f3f8fc] dark:bg-[#041d2e]">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-[#dbe8f1] bg-white px-4 py-3 sm:px-6 dark:border-[#14486a] dark:bg-[#072f4a]">
          <img src={logoNorthwindWide} alt="Northwind" className="h-8 w-auto" />
          <div className="flex items-center gap-3 text-sm text-[#0d3550] dark:text-[#e1f2ff]">
            <span className="hidden sm:inline">
              {session.email} · {session.can_edit ? "Can edit" : "View only"}
            </span>
            <button
              type="button"
              onClick={signOut}
              className="inline-flex items-center gap-1.5 rounded-lg border border-[#9ec6df] px-3 py-1.5 text-xs font-semibold text-[#064273] hover:bg-[#f6fbff] dark:border-[#0f6ea9] dark:text-[#e1f2ff]"
            >
              <LogOut className="h-3.5 w-3.5" />
              Sign out
            </button>
          </div>
        </header>
        <main className="mx-auto max-w-[1400px] px-4 py-6 sm:px-6">
          <ExternalCertifications />
        </main>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#f3f8fc] px-4 dark:bg-[#041d2e]">
      <div className="w-full max-w-md rounded-2xl border border-[#b8d3e6] bg-white p-6 shadow-sm dark:border-[#0a5f95] dark:bg-[#072f4a]">
        <img src={logoNorthwindWide} alt="Northwind" className="mb-5 h-9 w-auto" />
        <h1 className="flex items-center gap-2 text-lg font-semibold text-[#064273] dark:text-[#e1f2ff]">
          <ShieldCheck className="h-5 w-5" />
          External Certifications
        </h1>
        <p className="mt-1 text-sm text-[#4b738e] dark:text-[#b8dcf2]">
          {codeSent
            ? `Enter the 6-digit code sent to ${email}.`
            : "Enter your Northwind email to receive a verification code."}
        </p>

        {!codeSent ? (
          <form onSubmit={handleRequestCode} className="mt-5 space-y-3">
            <input
              type="email"
              required
              autoFocus
              placeholder="firstname.lastname@example.com"
              className={inputClass}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <button type="submit" disabled={busy} className={primaryButton}>
              {busy ? "Sending..." : "Send code"}
            </button>
          </form>
        ) : (
          <form onSubmit={handleVerify} className="mt-5 space-y-3">
            <input
              inputMode="numeric"
              autoComplete="one-time-code"
              required
              autoFocus
              maxLength={6}
              placeholder="123456"
              className={`${inputClass} tracking-[0.4em]`}
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
            />
            <button type="submit" disabled={busy || code.length !== 6} className={primaryButton}>
              {busy ? "Verifying..." : "Verify"}
            </button>
            <button
              type="button"
              onClick={() => {
                setCodeSent(false);
                setCode("");
                setError(null);
              }}
              className="w-full text-xs font-medium text-[#0a5f95] hover:underline dark:text-[#7cc4f2]"
            >
              Use another email / resend code
            </button>
          </form>
        )}

        {error && <p className="mt-3 text-sm text-rose-600">{error}</p>}
      </div>
    </div>
  );
}
