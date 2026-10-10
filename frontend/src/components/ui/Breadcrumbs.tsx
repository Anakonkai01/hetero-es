import { Fragment } from "react";
import { Link } from "react-router";

export interface Crumb {
  label: string;
  title?: string;
  to?: string;
}

export function Breadcrumbs({ crumbs }: { crumbs: Crumb[] }) {
  if (crumbs.length < 2) {
    return null;
  }

  return (
    <nav aria-label="Breadcrumb" className="crumbs">
      {crumbs.map((crumb, index) => {
        const isLast = index === crumbs.length - 1;

        if (isLast || !crumb.to) {
          return (
            <span
              key={index}
              className="cr cur"
              aria-current={isLast ? "page" : undefined}
              title={crumb.title ?? crumb.label}
            >
              {crumb.label}
            </span>
          );
        }

        return (
          <Fragment key={index}>
            <Link
              className="link cr"
              to={crumb.to}
              title={crumb.title ?? crumb.label}
            >
              {crumb.label}
            </Link>
            <span className="sep" aria-hidden="true">
              /
            </span>
          </Fragment>
        );
      })}
    </nav>
  );
}
