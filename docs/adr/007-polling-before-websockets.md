# ADR 007: Polling first, WebSockets in Phase 3

Date: 2026-10-19
Status: Accepted
Requirement: FR-12, FR-16 (customer tracking and the live queue)

## Context

The customer wants to know what happened to their order, and the shop wants to know when a new order arrives. Both are the same problem: the server has state that the browser would like to see change.

The customer page changes rarely. A status moves from paid to accepted to printing to ready over minutes. The vendor board changes more often, but a print shop takes in a few orders an hour, not a few a second.

## Decision

Poll, and do not open a WebSocket, in Phase 1.

- The customer order page polls every five seconds and stops when the order reaches a terminal status.
- The vendor board polls every five seconds and stops when the tab is in the background, so a forgotten tab on a counter screen does not keep the API busy.
- Polling stops for a hidden tab, for a terminal order, and for a page that is not open.

A WebSocket arrives in Phase 3, where the live queue and the wait estimates make it worth the extra machinery.

## Alternatives considered

1. **WebSockets from the start.** Rejected: the connection is a resource that has to be held, reconnected, and cleaned up when the tab closes, and the in-process pub-sub hub only works with one API instance, which the deployment does not have. For a status that changes every few minutes, a five second poll is a fraction of the traffic and none of the machinery. It also survives a laptop lid closing, which a WebSocket does not.
2. **Server sent events.** Rejected: a good middle ground, but it has the same connection lifecycle problems as a WebSocket, with fewer of the things a WebSocket can do. If the project needs push, it will want the full thing.
3. **A longer poll interval.** Rejected for the customer page and reconsidered for the board: five seconds is short enough that a change feels immediate and long enough that a shop with a few orders an hour is not making a request a second.

## Consequences

- There is no connection state on the server and nothing to clean up when a browser disappears.
- The API stays stateless, so the API can be scaled to more than one instance without the in-memory hub becoming a problem.
- A change is visible within five seconds. For a customer waiting for a shop to accept, that is the same as instant.
- The traffic is a poll every five seconds per open tab, which is small but not nothing. The rate limiter on the queue endpoint keeps one client from taking the budget for everyone.
- A WebSocket in Phase 3 will need a shared pub-sub if the API is ever scaled out. That is a documented cost of that phase, not of this one.

## Revisit trigger

If the poll traffic becomes measurable, if a status has to appear within a second, or if Phase 3 needs live updates across several screens at once, move to WebSockets. The trigger is written down so the decision is revisited on evidence rather than on taste.
