/** @odoo-module **/
import { Wysiwyg } from'@web_editor/js/wysiwyg/wysiwyg';
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
patch(Wysiwyg.prototype, {
   _getPowerboxOptions() {
       const options = super._getPowerboxOptions();
       options.categories.push({
           name: _t('Documentation'),
           priority: 300,
       });
       options.commands.push({
           name: _t('Document'),
           category: _t('Documentation'),
description: _t("Add this text to your mailing's     documentation"),
           fontawesome: 'fa-book',
           priority: 1,
           callback: this._onDocumentCommand.bind(this),
       });
       return options;
   },
   _onDocumentCommand() {
       // Define the document content to be inserted
       const documentContent = `
           <div class="document-content">
               <h2>Document Title</h2>
               <p>This is a paragraph of the document text added to your notes.</p>
               <ul>
                   <li>Item 1</li>
                   <li>Item 2</li>
                   <li>Item 3</li>
               </ul>
           </div>`;
           
       // Get the WYSIWYG editor instance
       const editor = this.$editable.data('wysiwyg');
       if (editor && editor.el) {
           // Insert the document content into the editor's element
           editor.el.innerHTML += documentContent;
       } else {
           console.error('Editor instance or editor element not found');
       }
   },
});