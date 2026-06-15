INTERNAL_ROLES = {"Admin", "DeliveryManager", "L1", "L2", "L3"}
PARTNER_ROLES = {"responsible", "technical"}
TICKET_TYPES = {
    "Problem",
    "Change Request",
    "New Feature",
    "Question",
    "Configuration",
    "Integration",
    "Security Issue",
    "Operational Request",
}
PRIORITIES = {"Low", "Normal", "High", "Critical"}
STATUSES = {"New", "Queued", "Need more info", "Assigned", "In progress", "Resolved", "Closed", "Rejected", "Duplicate", "Cancelled"}
RESOLVER_TEAMS = {"L1", "L2", "L3"}
GITLAB_STATUSES = {"Open", "To Do", "In Progress", "Done", "Closed"}

WORKFLOW_TRANSITIONS = {
    "New": {"Need more info", "Assigned", "Rejected", "Duplicate", "Cancelled"},
    "Queued": {"Assigned", "Need more info", "Rejected", "Cancelled"},
    "Need more info": {"New", "Queued", "Assigned", "Rejected", "Cancelled"},
    "Assigned": {"In progress", "Need more info", "Cancelled"},
    "In progress": {"Resolved", "Need more info", "Assigned"},
    "Resolved": {"Closed"},
    "Rejected": {"Closed"},
    "Duplicate": {"Closed"},
    "Cancelled": {"Closed"},
    "Closed": set(),
}
