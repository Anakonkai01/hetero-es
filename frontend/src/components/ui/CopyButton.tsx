import { useProduct } from '@heteroes/product-ui';
import { useAppState } from "../../app/appState";
import { CopyIcon } from "./Icons";

interface CopyButtonProps {
  value: string;
  subject: string;
}

export function CopyButton({ value, subject }: CopyButtonProps) {
  const {t}=useProduct();
  const { flash } = useAppState();

  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      flash("Full ID copied");
    } catch {
      flash("Copying is not available in this environment");
    }
  }

  return (
    <button
      type="button"
      className="ico"
      aria-label={`Copy full ${subject} ID`}
      title={t("Copy ID")}
      onClick={copy}
    >
      <CopyIcon />
    </button>
  );
}
