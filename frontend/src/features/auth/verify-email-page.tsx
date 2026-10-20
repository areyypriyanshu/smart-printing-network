import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";

import { Alert, linkClassName } from "../../components/ui";
import { messageForError } from "../../lib/errors";
import { AuthLayout } from "./auth-layout";
import { verifyEmailRequest } from "./api";
import { useSession } from "./session";

/**
 * The page the link in the message opens.
 *
 * The token is in the query string, because that is what a link in a
 * mail client can carry. It is read once, on arrival, and sent to the
 * server to be proved; the server keeps the hash, not the token.
 */
export function VerifyEmailPage() {
  const [searchParams] = useSearchParams();
  const { refreshUser } = useSession();
  const token = searchParams.get("token");
  const [result, setResult] = useState<"checking" | "verified" | "failed">(
    "checking",
  );
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (token === null || token === "") return;
    let cancelled = false;
    void (async () => {
      try {
        await verifyEmailRequest(token);
        if (cancelled) return;
        setResult("verified");
        await refreshUser();
      } catch (error) {
        if (cancelled) return;
        setResult("failed");
        setMessage(messageForError(error));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token, refreshUser]);

  const missingToken = token === null || token === "";

  return (
    <AuthLayout
      title="Confirm your email"
      subtitle="We check that the address belongs to you before you order a print."
      footer={
        <p className="border-t border-hairline pt-6 text-sm text-steel">
          Already confirmed?{" "}
          <Link className={linkClassName()} to="/login">
            Sign in
          </Link>
        </p>
      }
    >
      {missingToken && (
        <Alert>This link is not valid any more. Ask for a new one.</Alert>
      )}
      {!missingToken && result === "checking" && (
        <p role="status" className="text-steel">
          Checking your link…
        </p>
      )}
      {!missingToken && result === "verified" && (
        <Alert variant="success">
          Your email address is confirmed. You can order a print now.
        </Alert>
      )}
      {!missingToken && result === "failed" && (
        <>
          <Alert>{message}</Alert>
          <p className="text-sm text-steel">
            <Link className={linkClassName()} to="/account/email">
              Use a different email address
            </Link>
          </p>
        </>
      )}
    </AuthLayout>
  );
}
