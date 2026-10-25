import { Link } from "react-router";

import {
  CropMarks,
  Icon,
  buttonClassName,
  sectionTitleClassName,
  type IconName,
} from "../../components/ui";

const SAMPLE_SHOPS = [
  {
    name: "Kharghar Print Hub",
    area: "Sector 12, Kharghar",
    distance: "0.8 km",
    price: "₹ 38.40",
  },
  {
    name: "Station Road Xerox",
    area: "Kharghar",
    distance: "1.4 km",
    price: "₹ 42.00",
  },
  {
    name: "Chembur Copy Centre",
    area: "Chembur East",
    distance: "6.2 km",
    price: "₹ 35.20",
  },
];

const STEPS: Array<{ title: string; body: string; icon: IconName }> = [
  {
    title: "Upload your PDF",
    body: "We read the file, count the pages, and check it will print. You choose copies, colour, and sides.",
    icon: "upload",
  },
  {
    title: "Compare real prices",
    body: "Every shop publishes its own rates. You see the price from each shop before you decide.",
    icon: "store",
  },
  {
    title: "Collect with a code",
    body: "Reserve your prints, then show your pickup code at the counter and pay in cash when you collect.",
    icon: "pin",
  },
];

const TRUST_ITEMS: Array<{ title: string; body: string; icon: IconName }> = [
  {
    title: "Verified before listing",
    body: "Our team reviews every shop before customers can find it on the network.",
    icon: "check",
  },
  {
    title: "Prices from the shops themselves",
    body: "Each quote is computed from the shop's own rate card — never a guess or an estimate.",
    icon: "store",
  },
  {
    title: "Private by default",
    body: "Your PDF is shared only with the shop you choose, and deleted from storage after pickup.",
    icon: "file",
  },
];

const FAQS: Array<{ question: string; answer: string }> = [
  {
    question: "What can I print?",
    answer:
      "PDF files today: A4 documents in colour or black and white, single or double sided.",
  },
  {
    question: "How do I collect my prints?",
    answer:
      "You get a pickup code with your order. Show it at the counter once the shop accepts your job, and pay the shop's price in cash when you collect.",
  },
  {
    question: "Which shops are on the network?",
    answer:
      "Verified shops in Navi Mumbai and Mumbai today. More are added as they pass verification.",
  },
  {
    question: "Is there a fee to use it?",
    answer:
      "Creating an account is free. You pay the shop's listed price for each order.",
  },
];

function QuoteCard() {
  return (
    <article
      aria-label="Example quote"
      className="relative overflow-hidden rounded-xl border border-hairline bg-canvas shadow-1"
    >
      <div
        className="halftone absolute inset-0 opacity-60"
        aria-hidden="true"
      />
      <CropMarks />
      <div className="relative flex flex-col gap-5 p-6">
        <header className="flex items-baseline justify-between gap-3">
          <p className="font-mono text-xs uppercase tracking-[0.22em] text-steel">
            Example quote
          </p>
          <p className="font-mono text-xs text-steel">SPN-2419</p>
        </header>
        <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm sm:grid-cols-3">
          <div className="flex flex-col gap-1">
            <dt className="text-steel">Pages</dt>
            <dd className="font-mono text-ink">24 × 2</dd>
          </div>
          <div className="flex flex-col gap-1">
            <dt className="text-steel">Paper</dt>
            <dd className="font-mono text-ink">A4 · 75 gsm</dd>
          </div>
          <div className="flex flex-col gap-1">
            <dt className="text-steel">Ink</dt>
            <dd className="font-mono text-ink">Mono</dd>
          </div>
          <div className="flex flex-col gap-1">
            <dt className="text-steel">Sides</dt>
            <dd className="font-mono text-ink">Duplex</dd>
          </div>
          <div className="flex flex-col gap-1">
            <dt className="text-steel">Colour mode</dt>
            <dd className="font-mono text-ink">Auto</dd>
          </div>
          <div className="flex flex-col gap-1">
            <dt className="text-steel">Pickup</dt>
            <dd className="font-mono text-ink">Walk in</dd>
          </div>
        </dl>
        <ul className="flex flex-col gap-2 border-t border-hairline pt-5">
          {SAMPLE_SHOPS.map((shop) => (
            <li
              key={shop.name}
              className="flex items-center justify-between gap-3 rounded-lg border border-hairline px-3 py-2.5"
            >
              <span className="flex min-w-0 flex-col">
                <span className="truncate text-sm font-medium text-ink">
                  {shop.name}
                </span>
                <span className="text-xs text-steel">
                  {shop.area} · {shop.distance}
                </span>
              </span>
              <span className="font-mono text-sm text-ink">{shop.price}</span>
            </li>
          ))}
        </ul>
        <p className="text-xs text-steel">
          Sample data, shown for illustration. Your quotes use each shop&apos;s
          live rates.
        </p>
      </div>
    </article>
  );
}

export function LandingPage() {
  return (
    <>
      <section className="border-b border-hairline">
        <div className="mx-auto grid w-full max-w-6xl gap-12 px-4 py-14 lg:grid-cols-[1.05fr_0.95fr] lg:items-center lg:gap-16 lg:py-20">
          <div className="flex max-w-xl flex-col gap-6">
            <p className="font-mono text-xs uppercase tracking-[0.22em] text-steel">
              Verified print shops · Navi Mumbai
            </p>
            <h1 className="font-display text-4xl font-bold tracking-tight text-ink sm:text-5xl">
              Print from a shop near you
            </h1>
            <p className="text-lg text-steel">
              Upload a PDF, choose your print options and reserve it at a
              verified print shop. Collect it with a pickup code and pay in cash
              at the counter.
            </p>
            <div className="flex flex-wrap gap-3">
              <Link to="/register" className={buttonClassName("primary")}>
                Create an account
              </Link>
              <Link to="/login" className={buttonClassName("secondary")}>
                Sign in
              </Link>
            </div>
            <p className="text-sm text-steel">
              A4 documents in colour or black and white. No subscription — pay
              per order.
            </p>
          </div>
          <QuoteCard />
        </div>
      </section>

      <section className="border-b border-hairline">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-10 px-4 py-14 lg:py-20">
          <div className="flex max-w-xl flex-col gap-3">
            <h2 className="font-display text-3xl font-bold tracking-tight text-ink">
              From PDF to pick-up in three steps
            </h2>
            <p className="text-steel">
              No phone calls to the shop, no haggling at the counter.
            </p>
          </div>
          <ol className="grid gap-6 sm:grid-cols-3">
            {STEPS.map((step, index) => (
              <li
                key={step.title}
                className="flex flex-col gap-4 rounded-xl border border-hairline bg-canvas p-6"
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="inline-flex h-10 w-10 items-center justify-center rounded-lg border border-hairline bg-surface text-ink">
                    <Icon name={step.icon} size={20} />
                  </span>
                  <span className="font-mono text-xs text-steel">
                    0{index + 1}
                  </span>
                </div>
                <div className="flex flex-col gap-2">
                  <h3 className={sectionTitleClassName()}>{step.title}</h3>
                  <p className="text-sm text-steel">{step.body}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="border-b border-hairline bg-surface">
        <div className="mx-auto grid w-full max-w-6xl gap-8 px-4 py-14 sm:grid-cols-3 lg:py-20">
          {TRUST_ITEMS.map((item) => (
            <div key={item.title} className="flex flex-col gap-3">
              <Icon name={item.icon} size={22} className="text-primary-deep" />
              <h3 className={sectionTitleClassName()}>{item.title}</h3>
              <p className="text-sm text-steel">{item.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="border-b border-hairline">
        <div className="mx-auto w-full max-w-6xl px-4 py-14 lg:py-20">
          <div className="relative overflow-hidden rounded-xl border border-hairline bg-surface">
            <div
              className="halftone absolute inset-0 opacity-70"
              aria-hidden="true"
            />
            <CropMarks />
            <div className="relative flex flex-col gap-6 p-8 sm:p-10 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex max-w-xl flex-col gap-3">
                <h2 className="font-display text-3xl font-bold tracking-tight text-ink">
                  Run a print shop?
                </h2>
                <p className="text-steel">
                  Register your shop, publish your rates, and be ready for
                  pickup orders.
                </p>
              </div>
              <Link
                to="/register?as=shop"
                className={buttonClassName(
                  "primary",
                  "self-start lg:self-center",
                )}
              >
                Register your shop
              </Link>
            </div>
          </div>
        </div>
      </section>

      <section>
        <div className="mx-auto grid w-full max-w-6xl gap-8 px-4 py-14 lg:grid-cols-[minmax(0,20rem)_1fr] lg:gap-16 lg:py-20">
          <div className="flex flex-col gap-3">
            <h2 className="font-display text-3xl font-bold tracking-tight text-ink">
              Questions
            </h2>
            <p className="text-sm text-steel">
              The short answers before you print.
            </p>
          </div>
          <div className="flex flex-col">
            {FAQS.map((faq) => (
              <details
                key={faq.question}
                className="group border-b border-hairline first:border-t"
              >
                <summary className="flex min-h-14 cursor-pointer list-none items-center justify-between gap-3 py-3 text-base font-medium text-ink marker:content-none">
                  {faq.question}
                  <Icon
                    name="chevron-down"
                    size={18}
                    className="shrink-0 text-steel transition-transform duration-150 group-open:rotate-180 motion-reduce:transition-none"
                  />
                </summary>
                <p className="max-w-prose pb-4 text-sm text-steel">
                  {faq.answer}
                </p>
              </details>
            ))}
          </div>
        </div>
      </section>
    </>
  );
}
