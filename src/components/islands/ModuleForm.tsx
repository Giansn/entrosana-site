import { useEffect, useState } from "preact/hooks";
import { idle, send, type Status } from "../../lib/contact";
import StatusLine from "./StatusLine";

// One form for both directions of the modules market — a school or family
// requests a module, an educator proposes one. Same fields, one choice,
// instead of two identical forms in two modal dialogs.
// #propose or ?kind=proposal opens it in proposal mode.

type Kind = "request" | "proposal";

export default function ModuleForm({ mail }: { mail: string }) {
  const [kind, setKind] = useState<Kind>("request");
  const [status, setStatus] = useState<Status>(idle);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const k = new URLSearchParams(location.search).get("kind");
    if (k === "proposal" || location.hash === "#propose") setKind("proposal");
  }, []);

  const title = kind === "proposal" ? "Module proposal" : "Module request";

  const onSubmit = async (e: Event) => {
    e.preventDefault();
    const form = e.currentTarget as HTMLFormElement;
    const f = Object.fromEntries(new FormData(form)) as Record<string, string>;
    setBusy(true);
    setStatus({ state: "", parts: ["Sending…"] });
    const r = await send({
      name: f.name, email: f.email, org: f.org, interest: `${title} — ${f.area}`, msg: f.msg,
      subject: `${title}: ${f.area}`,
      body: `${title}\nName: ${f.name}\nEmail: ${f.email}\nYou are: ${f.org}\nArea: ${f.area}\n\n${f.msg}`,
      honeypot: f.website ?? "",
    });
    setStatus(r.status);
    setBusy(false);
    if (r.sent) { form.reset(); setKind("request"); }
  };

  return (
    <form class="form" id="module-form" action={`mailto:${mail}`} method="post" encType="text/plain" onSubmit={onSubmit}>
      <fieldset class="field">
        <legend>I want to</legend>
        <div class="choice">
          <label>
            <input type="radio" name="kind" value="request" checked={kind === "request"} onChange={() => setKind("request")} /> Request a module
          </label>
          <label>
            <input type="radio" name="kind" value="proposal" checked={kind === "proposal"} onChange={() => setKind("proposal")} /> Propose a module
          </label>
        </div>
      </fieldset>
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
          <span>You are</span>
          <select name="org" required>
            <option value="" disabled selected>Choose one…</option>
            <option>School</option>
            <option>Homeschooling family</option>
            <option>Association or non-profit</option>
            <option>Independent practitioner</option>
            <option>Other</option>
          </select>
        </label>
        <label class="field">
          <span>Area</span>
          <select name="area" required>
            <option value="" disabled selected>Choose one…</option>
            <option>Social</option>
            <option>Nature-based</option>
            <option>Technical</option>
            <option>Not sure yet</option>
          </select>
        </label>
      </div>
      <label class="field">
        <span>Details</span>
        <textarea name="msg" rows={5} required placeholder="Age group, group size, and roughly how long it should run." />
      </label>
      <div class="vh" aria-hidden="true">
        <label>Website <input name="website" type="text" tabIndex={-1} autocomplete="off" /></label>
      </div>
      <div class="form__foot">
        <button class="btn" type="submit" disabled={busy}>{kind === "proposal" ? "Send proposal" : "Send request"}</button>
        <StatusLine status={status} />
      </div>
      <p class="small muted">Storage for materials and records can be requested from entrosana as part of either. Goes to <a href={`mailto:${mail}`}>{mail}</a>.</p>
    </form>
  );
}
