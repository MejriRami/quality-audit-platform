import { BrowserRouter as Router, Routes, Route } from "react-router";
import { Toaster } from "react-hot-toast";
import SignIn from "./pages/AuthPages/SignIn";
import ResetPassword from "./pages/AuthPages/ResetPassword";
import NotFound from "./pages/OtherPage/NotFound";
import LineChart from "./pages/Charts/LineChart";
import BarChart from "./pages/Charts/BarChart";
import Calendar from "./pages/Calendar";
import BasicTables from "./pages/Tables/BasicTables";
import FormElements from "./pages/Forms/FormElements";
import KpiAudits from "./pages/Kpi/KpiAudits";
import AuditsCalendar from "./pages/AuditsCalendar/AuditsCalendar";
import AppLayout from "./layout/AppLayout";
import { ScrollToTop } from "./components/common/ScrollToTop";
import Framework from "./pages/Framework/Framework";
import Questionnaire from "./pages/Questionnaire/Questionnaire";
import AddQuestionnaire from "./components/questionnaire/add-questionnaire";
import AuditChecklist from "./components/audit/FillAudit";
import RequireAuth from "./components/auth/RequireAuth";
import RequireAdmin from "./components/auth/RequireAdmin";
import RequireRoleAccess from "./components/auth/RequireRoleAccess";
import { CarAccess } from "./components/CarAccess";
import AuditUnavailabilityForm from "./pages/Audit/AuditUnavailabilityForm";
import AuditeePortal from "./pages/Audit/AuditeePortal";
import ConsolidationReport from "./pages/Audit/ConsolidationReport";
import AdminControlCenter from "./pages/Admin/AdminControlCenter";
import PlantHolidays from "./pages/Admin/PlantHolidays";
import AuditPlanning from "./pages/Admin/AuditPlanning";
import ExternalCertifications from "./pages/ExternalCertifications/ExternalCertifications";
import CertificationsPortal from "./pages/ExternalCertifications/CertificationsPortal";
import RequireAuditAppAccess from "./components/auth/RequireAuditAppAccess";
import RequireCertificationAccess from "./components/auth/RequireCertificationAccess";

export default function App() {
  return (
    <>
      <Router>
        <ScrollToTop />
        <Toaster
          position="bottom-center"
          toastOptions={{
            duration: 4000,
          }}
        />
        <Routes>
          <Route path="/signin" element={<SignIn />} />
          <Route path="/reset-password" element={<ResetPassword />} />
          <Route path="/car-access" element={<CarAccess />} />
          <Route path="/auditee-portal" element={<AuditeePortal />} />
          <Route path="/certifications-portal" element={<CertificationsPortal />} />
          <Route
            path="/audit-unavailability"
            element={<AuditUnavailabilityForm />}
          />

          <Route element={<RequireAuth />}>
            <Route element={<AppLayout />}>
              <Route element={<RequireAuditAppAccess />}>
                <Route index path="/" element={<KpiAudits />} />
                <Route index path="/home" element={<KpiAudits />} />
                <Route path="/calendar" element={<Calendar />} />
                <Route path="/kpi-audits" element={<KpiAudits />} />
                <Route path="/form-elements" element={<FormElements />} />
                <Route path="/questionnaire" element={<Questionnaire />} />
                <Route path="/add-questionnaire" element={<AddQuestionnaire />} />
                <Route
                  path="/framework"
                  element={
                    <RequireRoleAccess mode="framework">
                      <Framework />
                    </RequireRoleAccess>
                  }
                />
                <Route
                  path="/plant-holidays"
                  element={
                    <RequireRoleAccess mode="holidays">
                      <PlantHolidays />
                    </RequireRoleAccess>
                  }
                />
                <Route
                  path="/audit-planning"
                  element={
                    <RequireRoleAccess mode="planning">
                      <AuditPlanning />
                    </RequireRoleAccess>
                  }
                />
                <Route path="/audits" element={<BasicTables />} />
                <Route
                  path="/audits/consolidation"
                  element={
                    <RequireRoleAccess mode="consolidation">
                      <ConsolidationReport />
                    </RequireRoleAccess>
                  }
                />
                <Route path="/audits-calendar" element={<AuditsCalendar />} />
                <Route path="/line-chart" element={<LineChart />} />
                <Route path="/bar-chart" element={<BarChart />} />
                <Route path="/fill" element={<AuditChecklist />} />
                <Route element={<RequireAdmin />}>
                  <Route
                    path="/admin/control-center"
                    element={<AdminControlCenter />}
                  />
                </Route>
              </Route>
              <Route element={<RequireCertificationAccess />}>
                <Route
                  path="/external-certifications"
                  element={<ExternalCertifications />}
                />
              </Route>
            </Route>
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </Router>
    </>
  );
}
