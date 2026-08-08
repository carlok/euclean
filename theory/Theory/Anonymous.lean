axiom Obj : Type

axiom R0 : Obj → Obj → Prop
axiom R1 : Obj → Obj → Obj → Prop
axiom R2 : Obj → Obj → Obj → Prop

axiom a0 : ∀ (v0 : Obj) (v1 : Obj) (v2 : Obj), R0 v0 v1 → R0 v1 v2 → R0 v0 v2
axiom a1 : ∀ (v0 : Obj) (v1 : Obj) (v2 : Obj) (v3 : Obj), R2 v0 v1 v2 → R1 v0 v2 v3 → v0 = v3
axiom a2 : ∀ (v0 : Obj) (v1 : Obj), ∃ (v2 : Obj), R2 v0 v1 v2
axiom a3 : ∀ (v0 : Obj) (v1 : Obj) (v2 : Obj) (v3 : Obj), R1 v0 v1 v2 → R0 v0 v3 → R0 v1 v3 → R0 v2 v3
axiom a4 : ∀ (v0 : Obj) (v1 : Obj) (v2 : Obj), R1 v0 v1 v2 → R0 v0 v2
axiom a5 : ∀ (v0 : Obj) (v1 : Obj), R0 v0 v1 → R0 v1 v0 → v0 = v1
axiom a6 : ∀ (v0 : Obj) (v1 : Obj) (v2 : Obj) (v3 : Obj), R2 v0 v1 v2 → R0 v3 v0 → R0 v3 v1 → R0 v3 v2
axiom a7 : ∀ (v0 : Obj) (v1 : Obj), ∃ (v2 : Obj), R1 v0 v1 v2
axiom a8 : ∀ (v0 : Obj) (v1 : Obj) (v2 : Obj), R1 v0 v1 v2 → R0 v1 v2
axiom a9 : ∀ (v0 : Obj) (v1 : Obj) (v2 : Obj) (v3 : Obj), R1 v0 v1 v2 → R2 v0 v2 v3 → v0 = v3
axiom a10 : ∀ (v0 : Obj) (v1 : Obj) (v2 : Obj) (v3 : Obj), R1 v0 v1 v2 → R1 v0 v1 v3 → v2 = v3
axiom a11 : ∀ (v0 : Obj) (v1 : Obj) (v2 : Obj), R2 v0 v1 v2 → R0 v2 v0
axiom a12 : ∀ (v0 : Obj) (v1 : Obj) (v2 : Obj), R2 v0 v1 v2 → R0 v2 v1
axiom a13 : ∀ (v0 : Obj) (v1 : Obj) (v2 : Obj) (v3 : Obj), R2 v0 v1 v2 → R2 v0 v1 v3 → v2 = v3
axiom a14 : ∀ (v0 : Obj), R0 v0 v0
