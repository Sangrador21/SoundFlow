import { useState } from "react";
import { Link2 } from "lucide-react";
import { useSoundFlow } from "../../app/SoundFlowProvider";
import { normalizeServers } from "../../config/servers";
import { errorMessage } from "../../utils/format";
import { Button } from "../../components/ui/Button";
import { Modal } from "../../components/ui/Modal";

export function ConnectionSettings({ onClose }: { onClose: () => void }) {
  const { servers, configure } = useSoundFlow();
  const [value, setValue] = useState(servers.join("\n"));
  const [error, setError] = useState("");
  return (
    <Modal title="Conectar servidores" onClose={onClose}>
      <form
        className="modal-body"
        onSubmit={(event) => {
          event.preventDefault();
          try {
            const urls = normalizeServers(
              value,
              location.protocol === "https:",
            );
            if (!urls.length) throw new Error("Agrega al menos una dirección.");
            configure(urls);
            onClose();
          } catch (reason) {
            setError(errorMessage(reason));
          }
        }}
      >
        <div className="setting-intro">
          <span className="setting-icon">
            <Link2 size={22} />
          </span>
          <p>Conecta tu biblioteca a uno o varios servidores de SoundFlow.</p>
        </div>
        <label className="field-label" htmlFor="servers">
          Direcciones de los servidores
        </label>
        <textarea
          id="servers"
          rows={4}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          placeholder={
            "https://tu-servidor-s1.onrender.com\nhttps://tu-servidor-s2.onrender.com"
          }
          aria-describedby="servers-hint"
        />
        <p id="servers-hint" className="field-hint">
          Una URL por línea. Se guardan en este navegador. Cambiarlas detendrá
          la reproducción actual.
        </p>
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        <div className="modal-actions">
          <Button variant="ghost" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit">Guardar conexión</Button>
        </div>
      </form>
    </Modal>
  );
}
