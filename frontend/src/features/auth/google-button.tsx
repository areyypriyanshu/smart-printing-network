import { useState } from "react";

import { Alert, Button } from "../../components/ui";
import { messageForError } from "../../lib/errors";
import { oauthStartRequest } from "./api";
import { openExternal } from "./oauth-navigation";

/**
 * The button that signs in with Google.
 *
 * It asks the server where to send the browser, and the browser goes
 * there. The server keeps the state in a signed cookie and the provider
 * sends the browser back to it, so the whole round trip happens in the
 * browser and nothing has to be kept on the server.
 */
export function GoogleButton({
  label = "Continue with Google",
}: {
  label?: string;
}) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onClick = async () => {
    setPending(true);
    setError(null);
    try {
      const { url } = await oauthStartRequest("google");
      openExternal(url);
    } catch (caught) {
      setError(messageForError(caught));
      setPending(false);
    }
  };

  return (
    <>
      <Button
        variant="secondary"
        onClick={() => void onClick()}
        pending={pending}
        pendingLabel="Opening Google…"
      >
        {label}
      </Button>
      {error !== null && <Alert>{error}</Alert>}
    </>
  );
}
