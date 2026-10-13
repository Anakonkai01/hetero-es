import { useProduct } from "@heteroes/product-ui";
import { GLOSSARY } from "../../lib/glossary";

/** A word with a short definition on hover or keyboard focus. */
export function Term({ term, children }: { term: keyof typeof GLOSSARY; children?: React.ReactNode }) {
  const { t } = useProduct();
  const definition = GLOSSARY[term];
  return <abbr className="term" tabIndex={0} title={t(definition)} data-definition={t(definition)}>{children ?? t(term)}</abbr>;
}
