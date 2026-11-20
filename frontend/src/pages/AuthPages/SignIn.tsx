import PageMeta from "../../components/common/PageMeta";
import AuthLayout from "./AuthPageLayout";
import SignInForm from "../../components/auth/SignInForm";

export default function SignIn() {
  return (
    <>
      <PageMeta
        title="Sign In | Northwind"
        description="Sign in to access audit management tools."
      />
      <AuthLayout>
        <SignInForm />
      </AuthLayout>
    </>
  );
}
