import type { CSSProperties } from "react";
import { Music2 } from "lucide-react";
export function Artwork({
  id = "",
  large = false,
  spinning = false,
}: {
  id?: string | undefined;
  large?: boolean;
  spinning?: boolean;
}) {
  const hue = 250 + (Number.parseInt(id.slice(0, 2) || "0", 16) % 35);
  return (
    <div
      className={large ? "artwork artwork--large" : "artwork"}
      style={{ "--art-hue": hue } as CSSProperties}
      aria-hidden="true"
    >
      {large ? (
        <div className={`vinyl ${spinning ? "vinyl--spinning" : ""}`}>
          <div className="vinyl-label">
            <Music2 size={25} strokeWidth={1.6} />
          </div>
        </div>
      ) : (
        <Music2 size={21} strokeWidth={1.6} />
      )}
    </div>
  );
}
