import { createContext, useContext } from "react";

export type Presentation = { on: boolean; set: (value: boolean) => void; toggle: () => void };
export const PresentationContext = createContext<Presentation>({ on: false, set: () => { }, toggle: () => { } });
export const usePresentation = () => useContext(PresentationContext);
