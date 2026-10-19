import { lazy } from "react";
import { Route, Routes } from "react-router";

import { Layout } from "./components/Layout";
import { NotFoundPage } from "./components/StatusPages";
import {
  LoginPage,
  RegisterPage,
  RegisterVendorPage,
  RequireAuth,
  RequireRole,
} from "./features/auth";
import { HomePage } from "./features/home/home-page";

const VendorRatesPage = lazy(() =>
  import("./features/vendor-rates/rates-page").then((module) => ({
    default: module.VendorRatesPage,
  })),
);

const VendorSettingsPage = lazy(() =>
  import("./features/vendor-settings/settings-page").then((module) => ({
    default: module.VendorSettingsPage,
  })),
);

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<HomePage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/register-vendor" element={<RegisterVendorPage />} />
        <Route
          path="/vendor/rates"
          element={
            <RequireAuth>
              <RequireRole role="vendor">
                <VendorRatesPage />
              </RequireRole>
            </RequireAuth>
          }
        />
        <Route
          path="/vendor/settings"
          element={
            <RequireAuth>
              <RequireRole role="vendor">
                <VendorSettingsPage />
              </RequireRole>
            </RequireAuth>
          }
        />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
