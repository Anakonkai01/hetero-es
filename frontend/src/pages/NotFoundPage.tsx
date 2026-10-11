import {useProduct} from '@heteroes/product-ui';
import { Link } from "react-router";

export function NotFoundPage() {
  const {t}=useProduct();
  return (
    <div className="card">
      <div className="empty">
        <b>{t("Page not found")}</b>
        <span>{t("The page you are looking for does not exist.")}</span>
        <Link className="btn pri" to="/dashboard">
          {t("Back to Dashboard")}</Link>
      </div>
    </div>
  );
}
