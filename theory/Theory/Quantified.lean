import Theory.Anonymous
set_option linter.unusedVariables false

def Q00 (x0 : Obj) (x2 : Obj) : Prop :=
  ∃ (x1 : Obj), (¬ (x0 = x1)) ∧ R0 x0 x1 x2

theorem Q00_intro (x0 : Obj) (x2 : Obj) (x1 : Obj) : (¬ (x0 = x1)) → R0 x0 x1 x2 → Q00 x0 x2 :=
  fun h0 => fun h1 => ⟨x1, (And.intro h0 h1)⟩

theorem Q00_elim (x0 : Obj) (x2 : Obj) : Q00 x0 x2 → ∃ (x1 : Obj), (¬ (x0 = x1)) ∧ R0 x0 x1 x2 :=
  fun h => h

def Q01 (x0 : Obj) (x2 : Obj) (x3 : Obj) : Prop :=
  ∃ (x1 : Obj), (¬ (x0 = x1)) ∧ ((¬ (x2 = x3)) ∧ R0 x0 x1 x2)

theorem Q01_intro (x0 : Obj) (x2 : Obj) (x3 : Obj) (x1 : Obj) : (¬ (x0 = x1)) → (¬ (x2 = x3)) → R0 x0 x1 x2 → Q01 x0 x2 x3 :=
  fun h0 => fun h1 => fun h2 => ⟨x1, (And.intro h0 (And.intro h1 h2))⟩

theorem Q01_elim (x0 : Obj) (x2 : Obj) (x3 : Obj) : Q01 x0 x2 x3 → ∃ (x1 : Obj), (¬ (x0 = x1)) ∧ ((¬ (x2 = x3)) ∧ R0 x0 x1 x2) :=
  fun h => h

def Q02 (x0 : Obj) (x1 : Obj) (x2 : Obj) (x4 : Obj) : Prop :=
  ∃ (x3 : Obj), (¬ (x0 = x1)) ∧ ((¬ (x2 = x3)) ∧ R0 x2 x3 x4)

theorem Q02_intro (x0 : Obj) (x1 : Obj) (x2 : Obj) (x4 : Obj) (x3 : Obj) : (¬ (x0 = x1)) → (¬ (x2 = x3)) → R0 x2 x3 x4 → Q02 x0 x1 x2 x4 :=
  fun h0 => fun h1 => fun h2 => ⟨x3, (And.intro h0 (And.intro h1 h2))⟩

theorem Q02_elim (x0 : Obj) (x1 : Obj) (x2 : Obj) (x4 : Obj) : Q02 x0 x1 x2 x4 → ∃ (x3 : Obj), (¬ (x0 = x1)) ∧ ((¬ (x2 = x3)) ∧ R0 x2 x3 x4) :=
  fun h => h

def Q03 (x0 : Obj) (x2 : Obj) (x3 : Obj) (x4 : Obj) : Prop :=
  ∃ (x1 : Obj), (¬ (x0 = x1)) ∧ ((¬ (x2 = x3)) ∧ R0 x0 x1 x4)

theorem Q03_intro (x0 : Obj) (x2 : Obj) (x3 : Obj) (x4 : Obj) (x1 : Obj) : (¬ (x0 = x1)) → (¬ (x2 = x3)) → R0 x0 x1 x4 → Q03 x0 x2 x3 x4 :=
  fun h0 => fun h1 => fun h2 => ⟨x1, (And.intro h0 (And.intro h1 h2))⟩

theorem Q03_elim (x0 : Obj) (x2 : Obj) (x3 : Obj) (x4 : Obj) : Q03 x0 x2 x3 x4 → ∃ (x1 : Obj), (¬ (x0 = x1)) ∧ ((¬ (x2 = x3)) ∧ R0 x0 x1 x4) :=
  fun h => h

def Q04 (x0 : Obj) (x2 : Obj) : Prop :=
  ∃ (x1 : Obj), (¬ (x0 = x1)) ∧ R0 x0 x2 x1

theorem Q04_intro (x0 : Obj) (x2 : Obj) (x1 : Obj) : (¬ (x0 = x1)) → R0 x0 x2 x1 → Q04 x0 x2 :=
  fun h0 => fun h1 => ⟨x1, (And.intro h0 h1)⟩

theorem Q04_elim (x0 : Obj) (x2 : Obj) : Q04 x0 x2 → ∃ (x1 : Obj), (¬ (x0 = x1)) ∧ R0 x0 x2 x1 :=
  fun h => h

def Q05 (x0 : Obj) (x1 : Obj) (x2 : Obj) (x4 : Obj) : Prop :=
  ∃ (x3 : Obj), (¬ (x0 = x1)) ∧ ((¬ (x2 = x3)) ∧ R0 x2 x4 x3)

theorem Q05_intro (x0 : Obj) (x1 : Obj) (x2 : Obj) (x4 : Obj) (x3 : Obj) : (¬ (x0 = x1)) → (¬ (x2 = x3)) → R0 x2 x4 x3 → Q05 x0 x1 x2 x4 :=
  fun h0 => fun h1 => fun h2 => ⟨x3, (And.intro h0 (And.intro h1 h2))⟩

theorem Q05_elim (x0 : Obj) (x1 : Obj) (x2 : Obj) (x4 : Obj) : Q05 x0 x1 x2 x4 → ∃ (x3 : Obj), (¬ (x0 = x1)) ∧ ((¬ (x2 = x3)) ∧ R0 x2 x4 x3) :=
  fun h => h
