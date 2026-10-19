const CHECKOUT_SCRIPT = "https://checkout.razorpay.com/v1/checkout.js";

type RazorpayResponse = {
  razorpay_payment_id: string;
  razorpay_order_id: string;
  razorpay_signature: string;
};

type RazorpayOptions = {
  key: string;
  amount: number;
  order_id: string;
  currency: string;
  name: string;
  description: string;
  handler: (response: RazorpayResponse) => void;
  modal?: { ondismiss?: () => void };
};

type RazorpayConstructor = new (options: RazorpayOptions) => {
  open: () => void;
};

declare global {
  interface Window {
    Razorpay?: RazorpayConstructor;
  }
}

export function loadCheckoutScript(): Promise<void> {
  if (document.querySelector(`script[src="${CHECKOUT_SCRIPT}"]`) !== null) {
    return Promise.resolve();
  }
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = CHECKOUT_SCRIPT;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () =>
      reject(new Error("Could not load the checkout script"));
    document.body.appendChild(script);
  });
}

export async function openCheckout(options: RazorpayOptions): Promise<void> {
  await loadCheckoutScript();
  const Razorpay = window.Razorpay;
  if (Razorpay === undefined) {
    throw new Error(
      "The checkout script loaded without a checkout constructor",
    );
  }
  new Razorpay(options).open();
}
