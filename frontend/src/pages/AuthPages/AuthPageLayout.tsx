import React from "react";
import GridShape from "../../components/common/GridShape";
import { Link } from "react-router";
import ThemeTogglerTwo from "../../components/common/ThemeTogglerTwo";
import logoNorthwind from "../../assets/logo/northwind.png";

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="relative bg-slate-50 z-1 dark:bg-slate-950 sm:p-0">
      <div className="relative flex flex-col justify-center w-full h-screen lg:flex-row sm:p-0">
        {children}
        <div
          className="items-center hidden w-full h-full lg:w-1/2 
  lg:grid 
  bg-gradient-to-b from-slate-900 to-slate-950 
  text-slate-100 
  border-r border-slate-900/30 
  shadow-[inset_0_0_0_1px_rgba(255,255,255,0.05)]"
        >
          <div className="relative flex items-center justify-center z-1">
            {/* <!-- ===== Common Grid Shape Start ===== --> */}
            <GridShape />
            <div className="flex flex-col items-center max-w-xs">
              <Link to="/" className="block mb-4">
                <img width={231} height={48} src={logoNorthwind} alt="Logo" />
              </Link>
              <p className="text-center text-slate-300">
                Secure audit workspace access
              </p>
            </div>
          </div>
        </div>
        <div className="fixed z-50 hidden bottom-6 right-6 sm:block">
          <ThemeTogglerTwo />
        </div>
      </div>
    </div>
  );
}
