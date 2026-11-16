import { MARK_PATHS, MARK_VIEWBOX } from "../../lib/mark";

export default function Mark({ size = 28, class: cls }: { size?: number; class?: string }) {
  return (
    <svg class={cls} width={size} height={size} viewBox={MARK_VIEWBOX} aria-hidden="true" focusable="false">
      {MARK_PATHS.map((d) => <path fill="currentColor" d={d} />)}
    </svg>
  );
}
