function formatBoolean(value) {
  if (value === true) {
    return 'Yes'
  }

  if (value === false) {
    return 'No'
  }

  return 'Not specified'
}

function getActiveGame(field) {
  return field?.active_game ?? field?.activeGame ?? null
}

function getPlayerCount(activeGame) {
  if (!activeGame) {
    return null
  }

  const currentPlayers = activeGame.current_players ?? activeGame.players_present
  const targetPlayers = activeGame.target_players ?? activeGame.max_players

  if (currentPlayers === undefined || targetPlayers === undefined) {
    return null
  }

  return `${currentPlayers} מתוך ${targetPlayers} שחקנים`
}

function getWaterCoolerValue(field) {
  return field.has_water_cooler ?? field.has_water
}

function FieldDetailsPanel({ field, onClose }) {
  if (!field) {
    return null
  }

  const activeGame = getActiveGame(field)
  const playerCount = getPlayerCount(activeGame)
  const status = field.approval_status ?? field.status ?? 'Not specified'
  const isPending = String(status).toLowerCase() === 'pending'

  return (
    <aside className="field-details-panel" aria-label="Field details">
      <button className="panel-close-button" type="button" onClick={onClose} aria-label="Close">
        x
      </button>

      <div className="panel-header">
        <h2>{field.name ?? 'Unnamed field'}</h2>
        {isPending ? <span className="approval-badge">Pending VAR approval</span> : null}
      </div>

      <dl className="field-details-list">
        <div>
          <dt>Surface type</dt>
          <dd>{field.surface_type ?? 'Not specified'}</dd>
        </div>
        <div>
          <dt>Has nets</dt>
          <dd>{formatBoolean(field.has_nets)}</dd>
        </div>
        <div>
          <dt>Has water cooler</dt>
          <dd>{formatBoolean(getWaterCoolerValue(field))}</dd>
        </div>
        <div>
          <dt>Opening hours</dt>
          <dd>{field.opening_hours ?? 'Not specified'}</dd>
        </div>
        <div>
          <dt>Notes</dt>
          <dd>{field.notes ?? 'No notes'}</dd>
        </div>
        <div>
          <dt>Status</dt>
          <dd>{status}</dd>
        </div>
      </dl>

      {activeGame ? (
        <div className="active-game-summary">
          <p>{playerCount ?? 'Active game available'}</p>
          <button type="button">Join</button>
        </div>
      ) : (
        <button className="primary-panel-button" type="button">
          Open Game
        </button>
      )}
    </aside>
  )
}

export default FieldDetailsPanel
