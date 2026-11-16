import type { Status } from "../../lib/contact";

/** Polite live region for form feedback; links stay real links. */
export default function StatusLine({ status }: { status: Status }) {
  return (
    <p class="form-status" role="status" aria-live="polite" data-state={status.state}>
      {status.parts.map((p, i) => (typeof p === "string" ? p : <a key={i} href={p[1]}>{p[0]}</a>))}
    </p>
  );
}
