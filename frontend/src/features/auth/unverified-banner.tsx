import { useState } from "react";
import { Link } from "react-router";

import { Alert, Button, linkClassName } from "../../components/ui";
import { messageForError } from "../../lib/errors";
import { resendVerificationRequest } from "./api";

/**
 * What a customer with an unproved address is told, wherever they are.
 *
 * The account works. The one thing that does not work is ordering a
 * print, because the address is what the printout and the pickup code
 * are tied to. The banner says so, offers to send the link again, and
 * offers the way out of a mistyped address.
 */
export function UnverifiedBanner({ email }: { email: string }) {
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const onResend = async () => {
    setPending(true);
    setError(null);
    try {
      await resendVerificationRequest();
      setSent(true);
    } catch (caught) {
      setError(messageForError(caught));
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="mx-auto w-full max-w-6xl px-4 pt-4">
      <Alert variant="info">
        <div className="flex flex-col gap-2">
          <p>
            Your email address is not confirmed yet. We need it before you order
            a print, because the printout and the pickup code are tied to it.
          </p>
          {sent && <p>We sent the link to {email} again.</p>}
          {error !== null && <p>{error}</p>}
          <div className="flex flex-wrap items-center gap-3">
            <Button
              variant="secondary"
              onClick={() => void onResend()}
              pending={pending}
              pendingLabel="Sending…"
            >
              Send the link again
            </Button>
            <Link className={linkClassName()} to="/account/email">
              Use a different email address
            </Link>
          </div>
        </div>
      </Alert>
    </div>
  );
}
