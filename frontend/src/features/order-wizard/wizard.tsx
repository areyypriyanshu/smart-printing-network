import { useState } from "react";
import { useSearchParams } from "react-router";

import type { UploadResponse } from "../../api/client";
import { Alert, Button, Stepper } from "../../components/ui";
import { messageForError } from "../../lib/errors";
import { useUpload } from "./api";
import { OptionsStep } from "./options-step";
import { PayStep } from "./pay-step";
import { ShopStep, type ShopSelection } from "./shop-step";
import { UploadStep } from "./upload-step";
import { OPTION_DEFAULTS, type OptionsFormValues } from "./schemas";

const STEPS = ["Upload", "Options", "Shop and price", "Review and pay"];

export function OrderWizardPage() {
  const [params, setParams] = useSearchParams();
  const urlUploadId = params.get("upload");
  const resume = useUpload(urlUploadId);

  const [upload, setUpload] = useState<UploadResponse | null>(null);
  const [options, setOptions] = useState<OptionsFormValues | null>(null);
  const [selectedShopId, setSelectedShopId] = useState<string | null>(null);
  const [selection, setSelection] = useState<ShopSelection | null>(null);
  const [step, setStep] = useState<number | null>(null);
  const [resumeDismissed, setResumeDismissed] = useState(false);

  const activeUpload =
    upload ?? (resumeDismissed ? null : (resume.data ?? null));
  const currentStep = step ?? (activeUpload !== null ? 1 : 0);

  const handleUploaded = (result: UploadResponse) => {
    setUpload(result);
    setOptions(null);
    setSelectedShopId(null);
    setSelection(null);
    setParams({ upload: result.id }, { replace: true });
    setStep(1);
  };

  const startOver = () => {
    setUpload(null);
    setOptions(null);
    setSelectedShopId(null);
    setSelection(null);
    setResumeDismissed(true);
    setStep(0);
    setParams({}, { replace: true });
  };

  if (
    urlUploadId !== null &&
    upload === null &&
    !resumeDismissed &&
    resume.isError
  ) {
    return (
      <section className="mx-auto flex w-full max-w-2xl flex-col gap-4 p-6">
        <h1 className="text-2xl font-semibold text-ink">New print order</h1>
        <Alert>{messageForError(resume.error)}</Alert>
        <div>
          <Button onClick={startOver}>Start a new order</Button>
        </div>
      </section>
    );
  }

  if (
    urlUploadId !== null &&
    upload === null &&
    !resumeDismissed &&
    resume.isPending
  ) {
    return (
      <section className="mx-auto flex w-full max-w-2xl flex-col gap-4 p-6">
        <h1 className="text-2xl font-semibold text-ink">New print order</h1>
        <p role="status" className="text-sm text-steel">
          Loading your upload…
        </p>
      </section>
    );
  }

  return (
    <section className="mx-auto flex w-full max-w-2xl flex-col gap-6 p-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold text-ink">New print order</h1>
        <Stepper steps={STEPS} current={currentStep + 1} />
        {currentStep > 0 && activeUpload !== null && (
          <p className="text-sm text-steel">
            {activeUpload.original_filename} ·{" "}
            {activeUpload.page_count === 1
              ? "1 page"
              : `${activeUpload.page_count} pages`}
          </p>
        )}
      </div>

      {currentStep === 0 && (
        <UploadStep
          upload={activeUpload}
          onUploaded={handleUploaded}
          onContinue={() => setStep(1)}
        />
      )}

      {currentStep === 1 && activeUpload !== null && (
        <OptionsStep
          defaultValues={options ?? OPTION_DEFAULTS}
          onBack={() => setStep(0)}
          onContinue={(values) => {
            setOptions(values);
            setSelectedShopId(null);
            setSelection(null);
            setStep(2);
          }}
        />
      )}

      {currentStep === 2 && activeUpload !== null && options !== null && (
        <ShopStep
          upload={activeUpload}
          options={options}
          selectedShopId={selectedShopId}
          onSelect={(value) => {
            setSelectedShopId(value.shop.id);
            setSelection(value);
          }}
          onContinue={() => setStep(3)}
          onBack={() => setStep(1)}
        />
      )}

      {currentStep === 3 &&
        activeUpload !== null &&
        options !== null &&
        selection !== null && (
          <PayStep
            upload={activeUpload}
            options={options}
            shop={selection.shop}
            quote={selection.quote}
            onBack={() => setStep(2)}
          />
        )}
    </section>
  );
}
