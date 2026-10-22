import { useEffect, useId, useRef, useState } from 'react';
import { useProduct } from '@heteroes/product-ui';

export function SearchSelect({
  id,
  label,
  value,
  options,
  onChange,
  disabled = false,
}: {
  id?: string;
  label: string;
  value: string;
  options: { value: string; label: string; disabled?: boolean }[];
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  const { t } = useProduct();
  const generated = useId();
  const listId = `${id ?? generated}-options`;
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const search = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);
  const filtered = options.filter((option) => option.label.toLocaleLowerCase().includes(query.toLocaleLowerCase()));
  const activeIndex = Math.max(0, Math.min(active, filtered.length - 1));
  const selected = options.find((option) => option.value === value);
  useEffect(() => {
    if (open) search.current?.focus();
    const outside = (event: PointerEvent) => {
      if (event.target instanceof Node && !root.current?.contains(event.target)) setOpen(false);
    };
    document.addEventListener('pointerdown', outside);
    return () => document.removeEventListener('pointerdown', outside);
  }, [open]);
  useEffect(() => {
    if (open) document.getElementById(`${listId}-${activeIndex}`)?.scrollIntoView({ block: 'nearest' });
  }, [open, activeIndex, listId, query]);
  const choose = (option: (typeof options)[number]) => {
    if (option.disabled) return;
    onChange(option.value);
    setOpen(false);
    trigger.current?.focus();
  };
  return (
    <div
      className="search-select"
      ref={root}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
      }}
      onKeyDown={(event) => {
        if (event.key === 'Escape') {
          setOpen(false);
          trigger.current?.focus();
        }
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
          event.preventDefault();
          setOpen(true);
          setActive((index) =>
            Math.max(0, Math.min(filtered.length - 1, open ? index + (event.key === 'ArrowDown' ? 1 : -1) : 0)),
          );
        }
        if (open && event.key === 'Enter') {
          event.preventDefault();
          if (filtered[activeIndex]) choose(filtered[activeIndex]);
        }
      }}
    >
      <button
        id={id}
        ref={trigger}
        type="button"
        className="sel"
        role="combobox"
        aria-label={label}
        aria-expanded={open}
        aria-controls={listId}
        aria-haspopup="listbox"
        disabled={disabled}
        title={selected?.label}
        onClick={() => {
          setQuery('');
          setActive(0);
          setOpen(!open);
        }}
      >
        <span>{selected?.label ?? label}</span>
        <span aria-hidden="true">⌄</span>
      </button>
      {open && (
        <div className="select-popover">
          <input
            ref={search}
            className="inp"
            type="search"
            aria-label={t('Search options')}
            aria-controls={listId}
            aria-activedescendant={filtered.length ? `${listId}-${activeIndex}` : undefined}
            placeholder={t('Search')}
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setActive(0);
            }}
          />
          <div id={listId} role="listbox" aria-label={label}>
            {filtered.map((option, index) => (
              <button
                type="button"
                role="option"
                id={`${listId}-${index}`}
                key={option.value}
                aria-selected={option.value === value}
                disabled={option.disabled}
                className={index === activeIndex ? 'option active' : 'option'}
                onClick={() => choose(option)}
                title={option.label}
              >
                <span>{option.label}</span>
                {option.value === value && <span aria-hidden="true">✓</span>}
              </button>
            ))}
            {!filtered.length && <p className="hint">{t('No results')}</p>}
          </div>
        </div>
      )}
    </div>
  );
}
