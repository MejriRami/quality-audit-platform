import PageMeta from "../../components/common/PageMeta";
import AuthLayout from "./AuthPageLayout";
import SignUpForm from "../../components/auth/SignUpForm";

export default function SignUp() {
  return (
    <>
      <PageMeta
        title="Create Account | Northwind"
        description="Create your account to access audit workflows."
      />
      <AuthLayout>
        <SignUpForm />
      </AuthLayout>
    </>
  );
}
