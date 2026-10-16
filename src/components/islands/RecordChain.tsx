import { useEffect, useState } from "preact/hooks";
import "../../styles/record.css";

// What "sealed record" means, shown instead of asserted. The seals arrive as
// props (real SHA-256, computed at build time in RecordChain.astro). "Rewrite"
// changes one entry after the fact; re-computing the chain in the browser
// then no longer matches the seals from that entry on.

export interface Entry { n: string; t: string; who: string; what: string; alt?: string }
interface Props {
  entries: Entry[];
  genesis: string;
  sealed: string[];
  /** the chain re-computed with the rewrite, for contexts without WebCrypto */
  rewrittenChain: string[];
}

const short = (h: string) => `${h.slice(0, 4)}…${h.slice(-4)}`;
const line = (prev: string, e: Entry, what: string) => `${prev}\n${e.n}|${e.t}|${e.who}|${what}`;

async function sha256(s: string): Promise<string> {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export default function RecordChain({ entries, genesis, sealed, rewrittenChain }: Props) {
  const [rewritten, setRewritten] = useState(false);
  const [ok, setOk] = useState<boolean[]>(() => entries.map(() => true));

  useEffect(() => {
    let live = true;
    (async () => {
      let chain: string[];
      if (globalThis.crypto?.subtle) {
        // the real check: re-compute every seal from the entries as they stand
        chain = [];
        let prev = genesis;
        for (const e of entries) {
          prev = await sha256(line(prev, e, rewritten && e.alt ? e.alt : e.what));
          chain.push(prev);
        }
      } else {
        // plain-http previews have no WebCrypto; same values, computed at build
        chain = rewritten ? rewrittenChain : sealed;
      }
      if (live) setOk(chain.map((h, i) => h === sealed[i]));
    })();
    return () => { live = false; };
  }, [rewritten]);

  const firstBad = ok.indexOf(false);

  return (
    <figure class="rc">
      <figcaption class="rc__cap"><span class="tag">Illustration · the sealed record</span></figcaption>
      <ol class="rc__log">
        {entries.map((e, i) => {
          const changed = rewritten && !!e.alt;
          return (
            <li class="rc__e" key={e.n} data-changed={changed || undefined}>
              <span class="rc__meta mono">#{e.n} · {e.t.slice(11)} · {e.who}</span>
              <span class="rc__what">{changed ? e.alt : e.what}</span>
              <span class="rc__seal mono">seal <code>{short(sealed[i])}</code></span>
              <span class="rc__check" data-ok={String(ok[i])}>
                <span aria-hidden="true">{ok[i] ? "✓" : "✗"}</span>
                <span class="vh">{ok[i] ? "matches its seal" : "does not match its seal"}</span>
              </span>
            </li>
          );
        })}
      </ol>
      <p class="rc__status mono" role="status" data-state={firstBad < 0 ? "ok" : "warn"}>
        {firstBad < 0
          ? `✓ Chain intact: all ${entries.length} entries match their seals.`
          : `✗ Entry ${entries[firstBad].n} was changed after it was sealed. Re-computed, no seal from there on matches.`}
      </p>
      <div class="rc__foot">
        <button class="btn btn--ghost rc__btn" type="button" aria-pressed={rewritten} onClick={() => setRewritten(!rewritten)}>
          {rewritten ? "Undo the rewrite" : "Rewrite entry 0142"}
        </button>
        <span class="rc__hint small muted">Change a decision after the fact, then watch the check.</span>
      </div>
    </figure>
  );
}
