import { BrowserRouter } from "react-router";

import { SessionProvider } from "./features/auth";
import { AppRoutes } from "./routes";

export function App() {
  return (
    <BrowserRouter>
      <SessionProvider>
        <AppRoutes />
      </SessionProvider>
    </BrowserRouter>
  );
}
