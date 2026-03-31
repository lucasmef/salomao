import type { PlanCard } from "../types";

type Props = {
  cards: PlanCard[];
};

export function SectionCards({ cards }: Props) {
  return (
    <section className="grid">
      {cards.map((card) => (
        <article key={card.title} className="module-card">
          <p className="eyebrow">{card.phase}</p>
          <h3>{card.title}</h3>
          <p>{card.description}</p>
        </article>
      ))}
    </section>
  );
}

