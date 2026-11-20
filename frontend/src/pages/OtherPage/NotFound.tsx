import GridShape from "../../components/common/GridShape";
import { Link } from "react-router";
import PageMeta from "../../components/common/PageMeta";

export default function NotFound() {
  return (
    <>
      <PageMeta
        title="Page Not Found | Northwind"
        description="The page you requested could not be found."
      />
      <div className="relative flex flex-col items-center justify-center min-h-screen bg-slate-50 p-6 overflow-hidden z-1">
        <GridShape />
        <div className="mx-auto w-full max-w-[242px] text-center sm:max-w-[472px]">
          <h1 className="mb-8 font-bold text-slate-900 text-title-md dark:text-white/90 xl:text-title-2xl">
            ERROR
          </h1>

          <img src="/images/error/404.svg" alt="404" className="dark:hidden" />
          <img
            src="/images/error/404-dark.svg"
            alt="404"
            className="hidden dark:block"
          />

          <p className="mt-10 mb-6 text-base text-slate-600 dark:text-slate-300 sm:text-lg">
            We can’t seem to find the page you are looking for!
          </p>

          <Link
            to="/"
            className="inline-flex items-center justify-center rounded-lg border border-slate-200 bg-white px-5 py-3.5 text-sm font-medium text-slate-700 shadow-theme-xs hover:bg-slate-50 hover:text-slate-900 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-white/[0.03] dark:hover:text-white"
          >
            Back to Home Page
          </Link>
        </div>
        {/* <!-- Footer --> */}
        <p className="absolute text-sm text-center text-slate-400 -translate-x-1/2 bottom-6 left-1/2 dark:text-slate-500">
          &copy; {new Date().getFullYear()} Northwind
        </p>
      </div>
    </>
  );
}
