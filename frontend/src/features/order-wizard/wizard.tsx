import { useState } from "react";
import { useLocation, useSearchParams } from "react-router";

import type { UploadResponse } from "../../api/client";
import {
  Alert,
  Button,
  pageTitleClassName,
  Stepper,
} from "../../components/ui";
import { messageForError } from "../../lib/errors";
import { useUpload } from "./api";
import { OptionsStep } from "./options-step";
import { PayStep } from "./pay-step";
import { ShopStep, type ShopSelection } from "./shop-step";
import { UploadStep } from "./upload-step";
import { useShops } from "../shops";
import {
  OPTION_DEFAULTS,
  PAYMENT_METHOD_DEFAULT,
  type OptionsFormValues,
  type PaymentMethod,
} from "./schemas";

const STEPS = ["Upload", "Options", "Shop and price", "Review and pay"];

/**
 * What "print this again" hands over: the copy of the file, the options
 * it was printed with, and the shop it was printed at. The customer can
 * change any of it.
 */
type ReorderState = {
  uploadId: string;
  options: OptionsFormValues;
  shopId: string;
};

export function OrderWizardPage() {
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const reorder = location.state as ReorderState | null;
  // A repeat print brings its own copy of the file with it.
  const urlUploadId = reorder?.uploadId ?? params.get("upload");
  const resume = useUpload(urlUploadId);

  const [upload, setUpload] = useState<UploadResponse | null>(null);
  const [options, setOptions] = useState<OptionsFormValues | null>(
    reorder?.options ?? null,
  );
  const [selectedShopId, setSelectedShopId] = useState<string | null>(
    reorder?.shopId ?? null,
  );
  const [selection, setSelection] = useState<ShopSelection | null>(null);
  const [step, setStep] = useState<number | null>(null);
  const [resumeDismissed, setResumeDismissed] = useState(false);
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>(
    PAYMENT_METHOD_DEFAULT,
  );
  // The same query the shop step uses, so the choice is only offered when
  // the server says it is on.
  const shops = useShops();

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
        <h1 className={pageTitleClassName()}>New print order</h1>
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
        <h1 className={pageTitleClassName()}>New print order</h1>
        <p role="status" className="text-sm text-steel">
          Loading your upload…
        </p>
      </section>
    );
  }

  return (
    <section className="mx-auto flex w-full max-w-2xl flex-col gap-6 p-6">
      <div className="flex flex-col gap-2">
        <h1 className={pageTitleClassName()}>New print order</h1>
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
            paymentMethod={paymentMethod}
            cashAtStoreEnabled={shops.data?.cash_at_store_enabled ?? false}
            onPaymentMethodChange={setPaymentMethod}
            onBack={() => setStep(2)}
          />
        )}
    </section>
  );
}
