import * as React from "react";
import { motion } from "framer-motion";

globalThis.__SKCT_REACT__ = React;

const suggestions = [
  "Tell me about AI & DS",
  "Which companies visited SKCT?",
  "Show faculty details",
  "What courses are offered?",
  "Tell me about placements"
];

export default function SuggestedQuestions({ onAsk }) {
  return (
    <div className="mx-auto mt-8 flex max-w-3xl flex-wrap justify-center gap-3">
      {suggestions.map((prompt, index) => (
        <motion.button
          key={prompt}
          type="button"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: index * 0.04 }}
          onClick={() => onAsk(prompt)}
          className="rounded-full border border-slate-200 bg-white/85 px-4 py-2.5 text-sm font-semibold text-slate-700 shadow-sm backdrop-blur transition hover:border-emerald-300 hover:bg-white hover:text-emerald-700"
        >
          {prompt}
        </motion.button>
      ))}
    </div>
  );
}
