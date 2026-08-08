axiom Obj : Type

axiom R0 : Obj → Obj → Obj → Prop
axiom R1 : Obj → Obj → Obj → Obj → Prop

axiom a0 : ∀ (v0 : Obj) (v1 : Obj) (v2 : Obj) (v3 : Obj) (v4 : Obj), (¬ (v3 = v4)) → R1 v0 v3 v0 v4 → R1 v1 v3 v1 v4 → R1 v2 v3 v2 v4 → R0 v0 v1 v2 ∨ R0 v1 v2 v0 ∨ R0 v2 v0 v1
axiom a1 : ∀ (v0 : Obj) (v1 : Obj) (v2 : Obj) (v3 : Obj) (v4 : Obj), R0 v0 v3 v4 → R0 v1 v3 v2 → (¬ (v0 = v3)) → ∃ (v5 : Obj) (v6 : Obj), R0 v0 v1 v5 ∧ R0 v0 v2 v6 ∧ R0 v5 v4 v6
axiom a2 : ∀ (v0 : Obj) (v1 : Obj) (v2 : Obj) (v3 : Obj) (v4 : Obj) (v5 : Obj), R1 v0 v1 v2 v3 → R1 v0 v1 v4 v5 → R1 v2 v3 v4 v5
axiom a3 : ∀ (v0 : Obj) (v1 : Obj) (v2 : Obj), R1 v0 v1 v2 v2 → v0 = v1
axiom a4 : ∀ (v0 : Obj) (v1 : Obj), R0 v0 v1 v0 → v0 = v1
axiom a5 : ∀ (v0 : Obj) (v1 : Obj) (v2 : Obj) (v3 : Obj), ∃ (v4 : Obj), R0 v0 v1 v4 ∧ R1 v1 v4 v2 v3
axiom a6 : ∃ (v0 : Obj) (v1 : Obj) (v2 : Obj), (¬ R0 v0 v1 v2) ∧ (¬ R0 v1 v2 v0) ∧ (¬ R0 v2 v0 v1)
axiom a7 : ∀ (v0 : Obj) (v1 : Obj) (v2 : Obj) (v3 : Obj) (v4 : Obj) (v5 : Obj) (v6 : Obj) (v7 : Obj), R1 v0 v2 v1 v3 → R1 v2 v4 v3 v5 → R1 v0 v6 v1 v7 → R1 v2 v6 v3 v7 → R0 v0 v2 v4 → R0 v1 v3 v5 → (¬ (v0 = v2)) → R1 v4 v6 v5 v7
axiom a8 : ∀ (v0 : Obj) (v1 : Obj), R1 v0 v1 v1 v0
axiom a9 : ∀ (v0 : Obj) (v1 : Obj) (v2 : Obj) (v3 : Obj) (v4 : Obj), R0 v0 v3 v2 → R0 v1 v4 v2 → ∃ (v5 : Obj), R0 v3 v5 v1 ∧ R0 v4 v5 v0
