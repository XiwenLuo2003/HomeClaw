// Run through mongosh in the deployment environment.  HomeClaw never executes
// this file automatically on a developer workstation.
db.preference_facts.createIndex(
  { user_id: 1, key: 1, scope: 1, scope_id: 1, valid_at: -1 }
);
// Exactly one currently active fact may exist for a user/key/scope tuple.
// MongoPreferenceStore retries duplicate-key and transient transaction races.
db.preference_facts.createIndex(
  { user_id: 1, key: 1, scope: 1, scope_id: 1 },
  { unique: true, partialFilterExpression: { invalid_at: null } }
);
db.preference_facts.createIndex(
  { invalid_at: 1, expires_at: 1 },
  { partialFilterExpression: { invalid_at: null } }
);
db.memory_events.createIndex({ user_id: 1, occurred_at: -1 });
db.memory_summaries.createIndex(
  { user_id: 1, period: 1, period_key: 1 },
  { unique: true }
);
