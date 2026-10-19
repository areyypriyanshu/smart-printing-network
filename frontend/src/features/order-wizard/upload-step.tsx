import { useRef, useState, type ChangeEvent, type DragEvent } from "react";

import { ApiError, type UploadResponse } from "../../api/client";
import { Alert, Button } from "../../components/ui";
import { messageForError } from "../../lib/errors";
import { uploadPdf } from "./api";

const MAX_UPLOAD_MB = 50;

type UploadStepProps = {
  upload: UploadResponse | null;
  onUploaded: (upload: UploadResponse) => void;
  onContinue: () => void;
};

function precheckError(file: File): string | null {
  if (file.size === 0) return "That file is empty.";
  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
    return `The file is larger than ${MAX_UPLOAD_MB} MB.`;
  }
  if (
    file.type !== "application/pdf" &&
    !file.name.toLowerCase().endsWith(".pdf")
  ) {
    return "That file is not a PDF.";
  }
  return null;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function UploadStep({
  upload,
  onUploaded,
  onContinue,
}: UploadStepProps) {
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [replacing, setReplacing] = useState(false);
  const handleRef = useRef<{ abort: () => void } | null>(null);
  const inputId = "wizard-file";

  const startUpload = (file: File) => {
    const message = precheckError(file);
    if (message !== null) {
      setError(message);
      return;
    }
    setError(null);
    setProgress(0);
    const handle = uploadPdf(file, setProgress);
    handleRef.current = handle;
    handle.promise.then(
      (result) => {
        handleRef.current = null;
        setProgress(null);
        setReplacing(false);
        onUploaded(result);
      },
      (cause: unknown) => {
        handleRef.current = null;
        setProgress(null);
        if (cause instanceof ApiError && cause.code === "ABORTED") return;
        setError(messageForError(cause));
      },
    );
  };

  const onFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file !== undefined) startUpload(file);
  };

  const onDrop = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    const file = event.dataTransfer.files[0];
    if (file !== undefined) startUpload(file);
  };

  if (progress !== null) {
    const percent = Math.round(progress * 100);
    return (
      <div className="flex flex-col gap-3 rounded-lg border border-beige-deep bg-cream p-6">
        <p role="status" className="text-sm text-ink">
          Uploading… {percent}%
        </p>
        <progress
          aria-label="Upload progress"
          max={100}
          value={percent}
          className="h-2 w-full"
        />
        <div>
          <Button
            variant="secondary"
            onClick={() => handleRef.current?.abort()}
          >
            Cancel upload
          </Button>
        </div>
      </div>
    );
  }

  if (upload !== null && !replacing) {
    return (
      <div className="flex flex-col gap-4 rounded-lg border border-beige-deep bg-cream p-6">
        <div>
          <h2 className="text-lg font-medium text-ink">File ready</h2>
          <p className="mt-1 text-sm text-ink">{upload.original_filename}</p>
          <p className="text-sm text-steel">
            {upload.page_count === 1 ? "1 page" : `${upload.page_count} pages`}{" "}
            · {formatSize(upload.size_bytes)}
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Button onClick={onContinue}>Continue</Button>
          <Button variant="secondary" onClick={() => setReplacing(true)}>
            Replace file
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {error !== null && <Alert>{error}</Alert>}
      <label
        htmlFor={inputId}
        onDrop={onDrop}
        onDragOver={(event) => event.preventDefault()}
        className="flex cursor-pointer flex-col items-center gap-2 rounded-lg border-2 border-dashed border-hairline-strong bg-surface p-10 text-center hover:border-primary"
      >
        <span className="text-sm font-medium text-ink">
          Drag a PDF here, or choose a file
        </span>
        <span className="text-xs text-steel">
          Up to {MAX_UPLOAD_MB} MB. Password-protected files are not supported.
        </span>
        <input
          id={inputId}
          type="file"
          accept="application/pdf"
          className="sr-only"
          onChange={onFileChange}
        />
      </label>
    </div>
  );
}
