from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CardMeta:
    card_id: int
    hp: int
    ex: bool
    mega_ex: bool
    tera: bool
    skill_texts: tuple[str, ...]
    attacks: tuple[int, ...]
    ace_spec: bool = False
    card_type: int | None = None
    name: str = ""
    basic: bool = False
    energy_type: int | None = None

    @property
    def prize_value(self) -> int:
        return 3 if self.mega_ex else 2 if self.ex else 1

    @property
    def is_basic_energy(self) -> bool:
        return 1 <= int(self.card_id) <= 8 or self.card_type == 5

    @property
    def is_special_energy(self) -> bool:
        return not 1 <= int(self.card_id) <= 8 and self.card_type == 6

    @property
    def is_energy(self) -> bool:
        return self.is_basic_energy or self.is_special_energy

    @property
    def is_fighting_pokemon(self) -> bool:
        return self.card_type == 0 and self.energy_type == 6

    @property
    def is_basic_team_rocket_pokemon(self) -> bool:
        normalized_name = self.name.replace("’", "'").lower()
        return (
            self.card_type == 0
            and self.basic
            and normalized_name.startswith("team rocket's ")
        )


class CardCatalog:
    def __init__(self, cards: dict[int, CardMeta], attack_text: dict[int, str]) -> None:
        self.cards = cards
        self.attack_text = attack_text

    @classmethod
    def from_records(
        cls, records: list[CardMeta], attack_text: dict[int, str]
    ) -> "CardCatalog":
        return cls({int(record.card_id): record for record in records},
                   {int(attack_id): str(text) for attack_id, text in attack_text.items()})

    @classmethod
    def empty(cls) -> "CardCatalog":
        return cls({}, {})

    @classmethod
    def from_cg(cls) -> "CardCatalog":
        from cg.api import all_attack, all_card_data

        cards = {
            int(card.cardId): CardMeta(
                card_id=int(card.cardId),
                hp=int(card.hp),
                ex=bool(card.ex),
                mega_ex=bool(card.megaEx),
                tera=bool(card.tera),
                skill_texts=tuple(str(skill.text) for skill in card.skills),
                attacks=tuple(int(attack_id) for attack_id in card.attacks),
                ace_spec=bool(card.aceSpec),
                card_type=int(card.cardType),
                name=str(card.name),
                basic=bool(card.basic),
                energy_type=(
                    None if card.energyType is None else int(card.energyType)
                ),
            )
            for card in all_card_data()
        }
        attacks = {
            int(attack.attackId): str(attack.text)
            for attack in all_attack()
        }
        return cls(cards, attacks)

    def card(self, card_id: int) -> CardMeta | None:
        return self.cards.get(int(card_id))

    def is_basic_energy(self, card_id: int) -> bool:
        meta = self.card(card_id)
        return 1 <= int(card_id) <= 8 or (
            meta is not None and meta.is_basic_energy
        )

    def is_special_energy(self, card_id: int) -> bool:
        meta = self.card(card_id)
        return (
            not 1 <= int(card_id) <= 8
            and meta is not None
            and meta.is_special_energy
        )
