import { useEffect, useRef, useState } from "preact/hooks";
import { idle, send, type Status } from "../../lib/contact";
import StatusLine from "./StatusLine";

// Request-access form. `?interest=<id>` (from a call to action elsewhere)
// preselects the topic. Without JS the form still works: it posts to the
// visitor's mail app (mailto action, plain text).

interface Props { interests: readonly { id: string; label: string }[]; mail: string }

export default function ContactForm({ interests, mail }: Props) {
  const [status, setStatus] = useState<Status>(idle);
  const [busy, setBusy] = useState(false);
  const select = useRef<HTMLSelectElement>(null);

  useEffect(() => {
    const want = new URLSearchParams(location.search).get("interest");
    const hit = interests.find((i) => i.id === want);
    if (hit && select.current) select.current.value = hit.label;
  }, []);

  const onSubmit = async (e: Event) => {
    e.preventDefault();
    const form = e.currentTarget as HTMLFormElement;
    const f = Object.fromEntries(new FormData(form)) as Record<string, string>;
    setBusy(true);
    setStatus({ state: "", parts: ["Sending…"] });
    const r = await send({
      name: f.name, email: f.email, org: f.org ?? "", interest: f.interest, msg: f.msg ?? "",
      subject: `Access request: ${f.interest}`,
      body: `Name: ${f.name}\nOrganisation: ${f.org || "—"}\nEmail: ${f.email}\nInterested in: ${f.interest}\n\n${f.msg || ""}`,
      honeypot: f.website ?? "",
    });
    setStatus(r.status);
    setBusy(false);
    if (r.sent) form.reset();
  };

  return (
    <form class="form" action={`mailto:${mail}`} method="post" encType="text/plain" onSubmit={onSubmit}>
      <div class="form__row">
        <label class="field">
          <span>Name</span>
          <input name="name" type="text" autocomplete="name" required />
        </label>
        <label class="field">
          <span>Email</span>
          <input name="email" type="email" autocomplete="email" required />
        </label>
      </div>
      <div class="form__row">
        <label class="field">
          <span>Organisation <span class="opt">(optional)</span></span>
          <input name="org" type="text" autocomplete="organization" />
        </label>
        <label class="field">
          <span>Interested in</span>
          <select name="interest" required ref={select}>
            <option value="" disabled selected>Choose one…</option>
            {interests.map((i) => <option key={i.id} value={i.label}>{i.label}</option>)}
          </select>
        </label>
      </div>
      <label class="field">
        <span>Message <span class="opt">(optional)</span></span>
        <textarea name="msg" rows={5} placeholder="One or two sentences is plenty." />
      </label>
      {/* honeypot: hidden from people and assistive tech */}
      <div class="vh" aria-hidden="true">
        <label>Website <input name="website" type="text" tabIndex={-1} autocomplete="off" /></label>
      </div>
      <div class="form__foot">
        <button class="btn" type="submit" disabled={busy}>Send request</button>
        <StatusLine status={status} />
      </div>
      <p class="small muted">Goes to <a href={`mailto:${mail}`}>{mail}</a>. We reply personally.</p>
    </form>
  );
}
