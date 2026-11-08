# Renofolio Consultation and Find My Style

The story numbers below follow the current US61 and can be aligned with the team's Final report.

## Demo

1. Log in as the demo Customer and open **Find My Style**. Choose Dining Room, a S$60,000 budget, Japandi and Completed Projects.
2. Compare **Best Matches** with **Other Options Within Budget**. Select **Show More** to reveal six more eligible projects. Open **Japandi Dining Room - Condominium, Clementi** and check that it matches the style and status and is S$3,000 below budget.
3. Click **Contact Designer** to open the bottom-right drawer. Write a message and send it.
4. In a separate browser session, log in as the demo Interior Designer and open **Messages**. Open the new enquiry and reply.
5. Return to the Customer drawer and select **Refresh**. Open **Messages** on another Customer page to see the same conversation in history.
6. In the Designer inbox, choose **Close Conversation** and confirm. Both participants can still open the history.
7. Close the Customer drawer and select **Back to My Matches** to return to the same answers and expanded results.
8. Try a S$10,000 Dining Room budget. The results show the lowest visible published budget of S$11,000. **Edit Budget** returns to the budget field.

## User Stories and Acceptance

| Story | User story | Acceptance |
|---|---|---|
| US62 | As a Customer, I want to contact the designer from a project page, so that I can discuss my renovation. | Contact Designer opens the project's conversation. Sending the first valid message creates a New consultation assigned to the project owner. A repeat first submission opens the existing thread. A hidden project or an empty message cannot start one. |
| US63 | As a Customer, I want to reopen my conversations and reply, so that I can keep track of the discussion. | The bottom-right Messages entry lists the signed-in Customer's history. An open, available thread accepts a reply and returns to New for the designer. Closed and unavailable threads remain readable. |
| US64 | As an Interior Designer, I want to receive, reply to and close project consultations, so that I can manage enquiries about my work. | The inbox lists enquiries assigned to that Designer. Sending a reply sets the thread to Replied. Confirming Close sets it to Closed. Other Designers cannot open or change that thread. |
| US65 | As a Customer, I want to answer a short renovation questionnaire, so that I can find projects suited to my requirements. | The questionnaire captures room, budget, style and preferred project status. Style choices include descriptions and a More Styles section. Results separate projects that meet every chosen preference from other projects within budget. Each card explains the match and the budget difference. Show More reveals additional projects. Back to My Matches restores the answers and result count. An empty result shows the lowest visible published room budget when available and links to the budget field. |

Suggested tasks for each story are to confirm the use case, draw the BCE and sequence diagrams, write the failing checks, implement the matching Boundary, Controller and Entity operations, and verify the normal and alternative flows. US62–US64 can use the shared consultation model below.

## BCE and Persistence

| Feature | Boundary | Controller | Entity |
|---|---|---|---|
| Consultation | `ConsultationPanel.show` and `submit` render the full page or drawer fragment. `Contact Designer` passes the project ID from Project Detail. | `ConsultationController.execute`, `send` and `close` verify the role and session. The signed-in account is the sender. | `Consultations` reads and writes the two participants' history. `InteriorDesignProjects.find` verifies a draft's public project. |
| Find My Style | `RenovationBriefPage.show` builds a `RenovationBriefRequest` from the four answers and requested result count. `ViewIDPDetailsPanel` keeps that context for the Back link. | `MatchRenovationBriefController.execute` validates the brief, ranks projects, groups matches and computes the remaining budget. | `InteriorDesignProjects.findForBrief` filters visible projects by room and budget. `lowestBudgetForRoom` uses the same room and visibility rules when there are no matches. |

SQLite creates `consultations` and `consultation_messages` on startup. A thread has a Customer, a Designer and a project title snapshot. Deleting a project clears the optional project reference while retaining the conversation. The first message and its thread are written together. A reply updates the status in the same transaction as its message.

The project category determines whether a style matches. Each matched style or status counts as one preference match. Lower published budget and project ID break ties in that order. The result page starts with six projects and shows six more per click. When neither preference is set, the results appear in a single **Projects Within Budget** group. Matching uses the designer's published budget as a reference.

## Main Sequences

~~~mermaid
sequenceDiagram
    actor Customer
    participant CPanel as ConsultationPanel
    participant CControl as ConsultationController
    participant CModel as Consultations
    actor Designer
    Customer->>CPanel: Contact Designer and submit first message
    CPanel->>CControl: send(request, CUSTOMER)
    CControl->>CModel: start(customerId, projectId, message)
    CModel-->>CControl: New thread or existing thread ID
    Designer->>CPanel: Open Messages and choose thread
    CPanel->>CControl: execute(request, INTERIOR_DESIGNER)
    CControl->>CModel: viewThread(threadId, designerId, role)
    Designer->>CPanel: Send Reply
    CPanel->>CControl: send(request, INTERIOR_DESIGNER)
    CControl->>CModel: reply(threadId, designerId, role, message)
    Customer->>CPanel: Refresh or reopen history
    CPanel->>CControl: execute(request, CUSTOMER)
    CControl->>CModel: viewThread(threadId, customerId, role)
~~~

~~~mermaid
sequenceDiagram
    actor Customer
    participant Page as RenovationBriefPage
    participant Control as MatchRenovationBriefController
    participant Projects as InteriorDesignProjects
    Customer->>Page: Submit room, budget, style and status
    Page->>Control: execute(RenovationBriefRequest)
    alt Valid answers
        Control->>Projects: findForBrief(room, budget)
        Projects-->>Control: Visible eligible projects
        alt Eligible projects
            Control-->>Page: Ranked groups, preference reasons and result count
        else No eligible projects
            Control->>Projects: lowestBudgetForRoom(room)
            Projects-->>Control: Lowest visible published budget, if available
            Control-->>Page: Empty result with available budget guidance
        end
    else Invalid answers
        Control-->>Page: Validation message
    end
    Page-->>Customer: Show matches or retain the form with feedback
~~~

## Test Evidence

The acceptance suite is `tests/test_consultations_and_matcher.py`. It covers both roles, conversation access and history, and the questionnaire's groups, budget feedback, additional styles and return links. The result files in `us62-us65-evidence/` record the original implementation checks and browser walkthrough.

For the results update, five checks failed on the earlier code and passed after implementation. The full suite passed all 449 tests. Desktop and 390px Chrome walkthroughs verified Show More, the return from a project after sending a consultation, Edit Budget and an additional style against a copy of the demo database.
