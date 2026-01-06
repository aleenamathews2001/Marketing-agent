import { LightningElement, api, track } from 'lwc';
import { ShowToastEvent } from 'lightning/platformShowToastEvent';
import { NavigationMixin } from 'lightning/navigation';

export default class PacepalChatbot extends NavigationMixin(LightningElement) {
    @api websocketUrl = 'wss://17837319a63b.ngrok-free.app/ws/chat';

    @track isChatOpen = false;
    @track currentMessage = '';
    @track connectionStatus = 'Disconnected';
    @track isSending = false;

    // Core Chat State
    @track messages = [];

    websocket = null;
    reconnectAttempts = 0;
    maxReconnectAttempts = 5;

    get connectionStatusClass() {
        return this.connectionStatus === 'Connected'
            ? 'status-indicator connected'
            : 'status-indicator disconnected';
    }

    // --- Lifecycle & WebSocket ---

    toggleChat() {
        this.isChatOpen = !this.isChatOpen;
        if (this.isChatOpen) {
            this.connectWebSocket();
        } else {
            this.disconnectWebSocket();
        }
    }

    connectWebSocket() {
        try {
            this.connectionStatus = 'Connecting...';
            this.websocket = new WebSocket(this.websocketUrl);

            this.websocket.onopen = () => {
                console.log('WebSocket connected');
                this.connectionStatus = 'Connected';
                this.reconnectAttempts = 0;
                this.addSystemMessage('Connected to Marketing Agent');
            };

            this.websocket.onmessage = (event) => {
                this.handleWebSocketMessage(event);
            };

            this.websocket.onclose = () => {
                console.log('WebSocket disconnected');
                this.connectionStatus = 'Disconnected';
                this.addSystemMessage('Disconnected from server');

                if (this.isChatOpen && this.reconnectAttempts < this.maxReconnectAttempts) {
                    this.reconnectAttempts++;
                    setTimeout(() => {
                        this.addSystemMessage(`Reconnecting... (Attempt ${this.reconnectAttempts})`);
                        this.connectWebSocket();
                    }, 3000);
                }
            };

            this.websocket.onerror = (error) => {
                console.error('WebSocket error:', error);
                this.connectionStatus = 'Error';
                this.showToast('Connection Error', 'Failed to connect to the server', 'error');
            };

        } catch (error) {
            console.error('Error connecting to WebSocket:', error);
            this.showToast('Connection Error', error.message, 'error');
        }
    }

    disconnectWebSocket() {
        if (this.websocket) {
            this.websocket.close();
            this.websocket = null;
        }
    }

    // --- Message Handling ---

    handleWebSocketMessage(event) {
        try {
            this.removeThinkingIndicator();
            const data = JSON.parse(event.data);
            console.log('Received:', data);

            if (data.type === 'status') {
                this.addSystemMessage(data.message);
            } else if (data.type === 'response') {
                this.isSending = false;
                if (data.success) {
                    this.addAgentMessage(data.response, data.created_records, data.salesforce_data);
                } else {
                    this.addErrorMessage(`Error: ${data.error || data.response}`);
                }
            } else if (data.type === 'review_proposal') {
                this.isSending = false;
                this.addReviewProposalMessage(data);
            } else if (data.type === 'error') {
                this.isSending = false;
                this.addErrorMessage(`Error: ${data.message}`);
            }
        } catch (error) {
            console.error('Error parsing message:', error);
            this.removeThinkingIndicator();
            this.isSending = false;
        }
    }

    // --- Message Array Management ---

    addSystemMessage(text) {
        this.pushMessage({ id: Date.now(), type: 'system', content: text, class: 'message message-system' });
    }

    addErrorMessage(text) {
        this.pushMessage({ id: Date.now(), type: 'error', content: text, class: 'message message-error' });
    }

    addUserMessage(text) {
        this.pushMessage({ id: Date.now(), type: 'user', content: text, class: 'message message-user' });
    }

    addAgentMessage(text, createdRecords, hasData) {
        const msgId = Date.now();
        let content = this.formatMessage(text);

        const messageObj = {
            id: msgId,
            type: 'agent',
            content: content,
            class: 'message message-agent',
            timestamp: new Date().toLocaleTimeString()
        };

        this.messages.push(messageObj);

        if (hasData && !createdRecords) {
            this.addSystemMessage('✓ Data processed');
        }

        if (createdRecords) {
            // Async enrichment
            this.enrichMessageWithLinks(msgId, text, createdRecords);
        }

        this.scrollToBottom();
    }

    // --- Helper to update filtered options ---
    updateFilteredOptions(msg) {
        // Robust normalization: ensure string, trim, lowercase
        const usedNames = new Set(
            msg.fields
                .map(f => f.name ? String(f.name).trim().toLowerCase() : '')
                .filter(n => n.length > 0)
        );

        // Debug: Log formatted list for clear verification (not Proxy)
        console.log('🔍 Used Fields List:', JSON.stringify(Array.from(usedNames)));

        const allOptions = (msg.availableFields || []).map(af => ({ label: af.label, value: af.name }));

        // Update fields with per-row options
        msg.fields = msg.fields.map(f => {
            if (f.isCustom) {
                // Determine options for this specific row
                const currentName = f.name ? String(f.name).trim().toLowerCase() : '';

                const rowOptions = allOptions.filter(opt => {
                    const optValue = String(opt.value).trim().toLowerCase();
                    const isUsed = usedNames.has(optValue);
                    const isCurrent = optValue === currentName;

                    // Keep if NOT used (available) OR if it is the current value (don't hide self)
                    return !isUsed || isCurrent;
                });

                return { ...f, rowOptions: rowOptions };
            }
            return f;
        });

        // Update global filteredAvailableFields (legacy, maybe used elsewhere?)
        msg.filteredAvailableFields = (msg.availableFields || []).filter(af =>
            !usedNames.has(String(af.name).trim().toLowerCase())
        );

        return msg;
    }

    addReviewProposalMessage(data) {
        // Special Message Type
        console.log('📦 Review Proposal Data RAW:', JSON.stringify(data));

        const proposal = data.proposal;
        const fields = proposal.fields || [];
        const relatedRecords = proposal.related_records || [];

        // FIX: Access available_fields from proposal object, not root data
        const availFields = proposal.available_fields || [];
        console.log('📋 Available Fields from backend:', availFields.length);

        const msgId = Date.now();
        let msg = {
            id: msgId,
            type: 'review',
            class: 'message message-review', // Blue emphasis class
            content: data.message,

            // Proposal State (contained within message)
            isReview: true,
            isEditing: false, // Start as Read-Only
            objectName: proposal.object,
            contactCount: proposal.contact_count,
            fields: fields.map(f => {
                const meta = availFields.find(af => af.name.toLowerCase() === f.name.toLowerCase());
                const isPicklist = meta && meta.type === 'picklist';
                return {
                    ...f,
                    key: f.name + msgId,
                    isPicklist: isPicklist,
                    picklistValues: isPicklist ? meta.picklistValues : []
                };
            }),
            relatedRecords: [], // Will be populated async
            availableFields: availFields,
            filteredAvailableFields: [], // Init
            fieldOptions: availFields.map(af => ({ label: af.label, value: af.name })), // ✅ For Combobox
            timestamp: new Date().toLocaleTimeString()
        };

        // Initial Filter
        msg = this.updateFilteredOptions(msg);

        console.log('✅ Final Message Object:', JSON.stringify(msg));

        this.messages.push(msg);

        // Async Link Generation for Related Records
        if (relatedRecords.length > 0) {
            this.enrichRelatedRecords(msgId, relatedRecords);
        }

        this.scrollToBottom();
    }

    async enrichRelatedRecords(msgId, records) {
        const processedRecords = [];

        for (const rec of records) {
            let url = '#';
            try {
                url = await this[NavigationMixin.GenerateUrl]({
                    type: 'standard__recordPage',
                    attributes: {
                        recordId: rec.Id,
                        actionName: 'view'
                    }
                });
            } catch (e) { console.error('Link gen failed', e); }

            processedRecords.push({
                id: rec.Id,
                name: rec.Name,
                email: rec.Email,
                url: url
            });
        }

        const msgIndex = this.messages.findIndex(m => m.id === msgId);
        if (msgIndex !== -1) {
            const newMsg = { ...this.messages[msgIndex] };
            newMsg.relatedRecords = processedRecords;
            this.messages[msgIndex] = newMsg;
        }
    }

    pushMessage(msg) {
        this.messages.push({
            ...msg,
            timestamp: new Date().toLocaleTimeString()
        });
        this.scrollToBottom();
    }

    // --- Review Proposal Interactions (Inline) ---

    handleToggleEdit(event) {
        const msgId = event.target.dataset.id;
        const msgIndex = this.messages.findIndex(m => m.id == msgId);
        if (msgIndex !== -1) {
            // Clone to trigger reactivity
            const newMsg = { ...this.messages[msgIndex] };
            newMsg.isEditing = !newMsg.isEditing; // Toggle
            this.messages[msgIndex] = newMsg;
        }
    }

    handleFieldChange(event) {
        const msgId = event.target.dataset.msgid;
        const fieldName = event.target.dataset.name;
        const newVal = event.target.value;

        const msgIndex = this.messages.findIndex(m => m.id == msgId);
        if (msgIndex !== -1) {
            const newMsg = { ...this.messages[msgIndex] };
            newMsg.fields = newMsg.fields.map(f => {
                if (f.name === fieldName) return { ...f, value: newVal };
                return f;
            });
            this.messages[msgIndex] = newMsg;
        }
    }

    handleProceed(event) {
        const msgId = event.target.dataset.id;
        const msg = this.messages.find(m => m.id == msgId);
        if (!msg) return;

        // Construct confirmation logic
        let confirmMsg = `Proceed with creating ${msg.objectName}. `;
        const updates = [];
        msg.fields.forEach(field => {
            if (field.value) updates.push(`${field.name}='${field.value}'`);
        });
        confirmMsg += `Details: ${updates.join(', ')}.`;

        this.sendCustomMessage(confirmMsg);

        // Mark as Processed (remove buttons? or just leave them)
        // User might want to proceed again? Probably safer to leave or disable?
        // Let's hide the buttons to prevent double submit for now, or just leave as history.
        // For UI cleanliness, let's switch it back to Read Only
        if (msg.isEditing) {
            const msgIndex = this.messages.findIndex(m => m.id == msgId);
            this.messages[msgIndex] = { ...msg, isEditing: false };
        }
    }

    // --- Helpers ---

    async enrichMessageWithLinks(msgId, text, recordsMap) {
        // Find message
        let msgIndex = this.messages.findIndex(m => m.id === msgId);
        if (msgIndex === -1) return;

        let enrichedText = text;
        let hasUpdates = false;

        for (const [objectApiName, records] of Object.entries(recordsMap)) {
            for (const record of records) {
                try {
                    const url = await this[NavigationMixin.GenerateUrl]({
                        type: 'standard__recordPage',
                        attributes: {
                            recordId: record.Id,
                            objectApiName: objectApiName,
                            actionName: 'view'
                        }
                    });

                    const linkHtml = `<a href="${url}" target="_blank" style="color: #005fb2; text-decoration: underline; font-weight: bold;">${record.Name}</a>`;
                    const escapedName = record.Name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                    const nameRegex = new RegExp(escapedName, 'gi');

                    if (nameRegex.test(enrichedText)) {
                        enrichedText = enrichedText.replace(nameRegex, linkHtml);
                        hasUpdates = true;
                    } else if (enrichedText.includes(record.Id)) {
                        enrichedText = enrichedText.replace(record.Id, linkHtml);
                        hasUpdates = true;
                    } else {
                        enrichedText += ` <br/>View: ${linkHtml}`;
                        hasUpdates = true;
                    }
                } catch (e) { console.error(e); }
            }
        }

        if (hasUpdates) {
            // Update Array Reactively
            const newMsg = { ...this.messages[msgIndex] };
            newMsg.content = this.formatMessage(enrichedText, true);
            this.messages[msgIndex] = newMsg;
        }
    }

    formatMessage(text, skipMarkdown = false) {
        if (!text) return '';
        let formatted = text;
        if (!skipMarkdown) {
            formatted = formatted.replace(
                /\[([^\]]+)\]\(([^)]+)\)/g,
                '<a href="$2" target="_blank" style="color: #005fb2; text-decoration: underline;">$1</a>'
            );
        }
        return formatted.replace(/\n/g, '<br/>');
    }

    scrollToBottom() {
        // Need to wait for DOM update
        setTimeout(() => {
            const container = this.template.querySelector('.chat-messages');
            if (container) container.scrollTop = container.scrollHeight;
        }, 100);
    }

    // --- Review Mode Handlers ---

    handleToggleEdit(event) {
        const msgId = event.target.dataset.id;
        const msgIndex = this.messages.findIndex(m => m.id == msgId);
        if (msgIndex !== -1) {
            // Clone to trigger reactivity
            const newMsg = { ...this.messages[msgIndex] };
            newMsg.isEditing = !newMsg.isEditing;
            this.messages[msgIndex] = newMsg;
        }
    }

    handleAddField(event) {
        const msgId = event.target.dataset.id;
        const msgIndex = this.messages.findIndex(m => m.id == msgId);
        if (msgIndex === -1) return;

        let newMsg = { ...this.messages[msgIndex] };
        // Create a unique key
        const newKey = 'custom_' + Date.now();

        newMsg.fields = [...newMsg.fields, {
            key: newKey,
            name: '',   // User edits this
            value: '',  // User edits this
            label: 'New Field',
            isCustom: true,
            isPicklist: false,
            picklistValues: []
        }];

        // Re-filter options
        newMsg = this.updateFilteredOptions(newMsg);

        this.messages[msgIndex] = newMsg;

        // Scroll to make sure new field is visible
        this.scrollToBottom();
    }

    handleFieldChange(event) {
        const msgId = event.target.dataset.msgid;
        const fieldKey = event.target.dataset.key; // Stable ID
        const property = event.target.dataset.property; // 'name' or 'value'
        const newVal = event.target.value;

        const msgIndex = this.messages.findIndex(m => m.id == msgId);
        if (msgIndex !== -1) {
            let newMsg = { ...this.messages[msgIndex] };
            const availableFields = newMsg.availableFields || [];

            newMsg.fields = newMsg.fields.map(f => {
                if (f.key === fieldKey) {
                    let updatedField = { ...f };

                    if (property === 'name') {
                        updatedField.name = newVal;

                        // Check if this field name exists in availableFields
                        const meta = availableFields.find(af => af.name === newVal);
                        if (meta) {
                            updatedField.label = meta.label; // ✅ Update Label!

                            if (meta.type === 'picklist') {
                                updatedField.isPicklist = true;
                                updatedField.picklistValues = meta.picklistValues;
                                updatedField.value = ''; // Reset value on field change
                            } else {
                                updatedField.isPicklist = false;
                                updatedField.picklistValues = [];
                            }
                        } else {
                            updatedField.label = newVal; // Fallback
                            updatedField.isPicklist = false;
                        }
                    } else if (property === 'value') {
                        updatedField.value = newVal;
                    }
                    return updatedField;
                }
                return f;
            });

            // Re-filter options on name change
            if (property === 'name') {
                newMsg = this.updateFilteredOptions(newMsg);
            }

            this.messages[msgIndex] = newMsg;
        }
    }

    handleProceed(event) {
        const msgId = event.target.dataset.id;
        const msg = this.messages.find(m => m.id == msgId);
        if (!msg) return;

        // Construct confirmation logic
        let confirmMsg = `Proceed with creating ${msg.objectName}. `;
        const updates = [];

        msg.fields.forEach(field => {
            // Only add if value exists. For custom fields, Name must also exist.
            if (field.value && field.name) {
                updates.push(`${field.name}='${field.value}'`);
            }
        });

        confirmMsg += `Details: ${updates.join(', ')}.`;

        // Pass related records context if available
        if (msg.relatedRecords && msg.relatedRecords.length > 0) {
            const ids = msg.relatedRecords.map(r => r.id).join(', ');
            // Explicitly key off "CampaignMember" so backend rule triggers
            confirmMsg += ` AND Create CampaignMember records for the following ${msg.relatedRecords.length} found records: [${ids}]`;
        }

        this.sendCustomMessage(confirmMsg, 'Proceeding with the proposed details...');

        // Switch back to Read Only
        if (msg.isEditing) {
            const msgIndex = this.messages.findIndex(m => m.id == msgId);
            this.messages[msgIndex] = { ...msg, isEditing: false };
        }
    }

    // --- Input Handling ---

    handleMessageChange(event) { this.currentMessage = event.target.value; }

    handleKeyPress(event) {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            this.sendMessage();
        }
    }

    sendMessage(uiLabel = null) {
        if (!this.currentMessage.trim()) return;
        if (!this.websocket || this.websocket.readyState !== WebSocket.OPEN) {
            this.showToast('Not Connected', 'Wait for connection', 'warning');
            return;
        }

        // Fix: onclick passes an Event object as first arg. Ensure uiLabel is a string or null.
        let displayLabel = null;
        if (typeof uiLabel === 'string') {
            displayLabel = uiLabel;
        }

        // Use uiLabel if provided (cleaner UI), otherwise show the full message
        this.addUserMessage(displayLabel || this.currentMessage);

        try {
            this.websocket.send(JSON.stringify({ message: this.currentMessage }));
            this.isSending = true;
            this.addThinkingIndicator();
            this.currentMessage = '';
        } catch (error) {
            this.isSending = false;
            this.removeThinkingIndicator();
        }
    }

    sendCustomMessage(msg, uiLabel = null) {
        this.currentMessage = msg;
        this.sendMessage(uiLabel);
    }

    // --- Thinking Indicator (Now just a special message?) ---
    // Actually simpler to just have a boolean isThinking and render it in HTML 
    // BUT to keep message structure, let's just append a temporary message

    addThinkingIndicator() {
        this.pushMessage({
            id: 'thinking',
            type: 'thinking',
            content: '',
            class: 'message message-agent thinking-message',
            isThinking: true
        });
    }

    removeThinkingIndicator() {
        this.messages = this.messages.filter(m => m.type !== 'thinking');
    }

    showToast(title, message, variant) {
        this.dispatchEvent(new ShowToastEvent({ title, message, variant }));
    }

    disconnectedCallback() {
        this.disconnectWebSocket();
    }
}