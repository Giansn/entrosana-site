// Sending for the contact and module forms (used by the Preact islands).
//
// A form posts JSON (name, org, email, interest, msg) to the endpoint. On the
// live site that is /api/contact on the same host: the web server hands it to
// the Hub's API, which mails it to info@ with the sender as reply address and
// stores nothing. PUBLIC_CONTACT_ENDPOINT overrides the address at build time.
// Set it to an empty value, or build under a base path (a preview on a static
// host has no backend), and the same message is composed in the visitor's
// mail app instead. Either way, what was typed stays on screen until it has
// really gone out.
import { MAIL } from "./site";

const SET = import.meta.env.PUBLIC_CONTACT_ENDPOINT as string | undefined;
const ENDPOINT: string | undefined =
  SET !== undefined ? SET || undefined : import.meta.env.BASE_URL === "/" ? "/api/contact" : undefined;

/** Status line: text, with [label, href] pairs rendered as links. */
export interface Status { state: "" | "ok" | "warn"; parts: (string | [string, string])[] }
export const idle: Status = { state: "", parts: [] };

export interface Message {
  name: string; email: string; org: string; interest: string; msg: string;
  subject: string; body: string;
  honeypot: string;
}

export async function send(m: Message): Promise<{ status: Status; sent: boolean }> {
  // honeypot: people never see this field, bots fill it in
  if (m.honeypot) return { status: { state: "ok", parts: ["Sent."] }, sent: true };

  const mailto = `mailto:${MAIL}?subject=${encodeURIComponent(m.subject)}&body=${encodeURIComponent(m.body)}`;

  if (!ENDPOINT) {
    location.href = mailto;
    return {
      sent: false,
      status: { state: "ok", parts: [
        "Your mail app opens with the message filled in. Nothing opened? ",
        ["Try again", mailto], " or write to ", [MAIL, `mailto:${MAIL}`], ".",
      ] },
    };
  }

  try {
    const r = await fetch(ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: m.name, org: m.org, email: m.email, interest: m.interest, msg: m.msg }),
    });
    if (!r.ok) {
      const j = await r.json().catch(() => ({}));
      throw new Error(r.status === 429 ? "Too many messages from here in the last hour." : (j && j.error) || "Sending failed.");
    }
    return { status: { state: "ok", parts: ["Sent."] }, sent: true };
  } catch (err) {
    return {
      sent: false,
      status: { state: "warn", parts: [
        `${err instanceof Error ? err.message : "Sending failed."} Your text is still here: `,
        ["send it from your mail app", mailto], ".",
      ] },
    };
  }
}
