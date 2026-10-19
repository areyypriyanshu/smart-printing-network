# ADR 009: A payment gateway interface with a fake implementation

Date: 2026-10-19
Status: Accepted
Requirement: FR-8, FR-13 (order, payment and refunds)

## Context

The application has to talk to a payment provider: create a gateway order, verify a webhook signature, and refund a payment. The provider is Razorpay, in test mode, and the project is not allowed to move real money.

A test suite that calls a real provider is slow, needs network access, needs credentials, and fails for reasons that have nothing to do with the code. It also cannot easily test the cases that matter most: a duplicate webhook, a wrong amount, a gateway that is down at exactly the wrong moment.

## Decision

Put the provider behind a `PaymentGateway` protocol in `app/gateways/payments/`, and ship two implementations.

```python
class PaymentGateway(Protocol):
    provider: str
    checkout_key_id: str | None

    def create_order(self, *, amount_paise: int, receipt: str, currency: str = "INR") -> GatewayOrder: ...
    def verify_webhook_signature(self, *, raw_body: bytes, signature: str) -> bool: ...
    def refund(self, *, provider_payment_id: str, amount_paise: int, idempotency_note: str) -> GatewayRefund: ...
```

- `RazorpayGateway` calls the real API. It uses `urllib` from the standard library rather than adding the `razorpay` package, so the dependency surface of the backend stays at the packages this project actually needs. The request builders are pure functions and are unit tested without a network.
- `FakeGateway` signs with HMAC-SHA256 over the same raw bytes and can produce signed webhook payloads. It is what the test suite, the local stack and the "simulate payment" endpoint use.
- `build_payment_gateway(settings)` picks one from the `PAYMENT_PROVIDER` setting. `PAYMENT_PROVIDER=fake` is the default, and the setting refuses to start without all three Razorpay credentials when the provider is `razorpay`.

The interface is a `Protocol`, not a base class, so an implementation does not have to inherit from anything and the gateway module stays free of framework imports.

## Alternatives considered

1. **Call Razorpay directly from the services.** Rejected: every test that touched money would need credentials and a network, and the awkward cases would be untestable.
2. **Use the official `razorpay` package.** Rejected for now: the HTTP surface this project needs is one order endpoint and one refund endpoint. The standard library covers that, and a dependency is a thing that can break, has to be audited, and has to be kept in step with the provider. If the provider's API grows, the package becomes worth adding.
3. **Mock the gateway in the tests with a mocking library.** Rejected: a mock has to be re written for every call the code makes, and it says nothing about what the real adapter does. A second real implementation, the fake, is used by the tests, the local stack and the demo, so it is exercised in the same way the real one is.

## Consequences

- The whole test suite runs without a network and without credentials.
- The local stack can demo the full order flow, including a signed webhook, with `PAYMENT_PROVIDER=fake`.
- The `simulate-payment` endpoint exists only outside production, and it refuses to run when the configured provider is not the fake one. Both are tested.
- The gateway interface is a seam, so a second provider, or a different refund flow, can be added without touching the services. The cost is that the interface has to be kept honest: if a provider needs something the interface cannot express, the interface grows or the provider needs its own adapter.

## Revisit trigger

If the project takes real money, adds a second payment provider, or needs a feature the interface cannot express, for example split payments or a saved card, revisit the shape of the interface rather than working around it in a service.
