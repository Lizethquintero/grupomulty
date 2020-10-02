# -*- coding: utf-8 -*-
# Copyright 2017 Marlon Falcón Hernandez
# Copyright 2019 Joan Marín <Github@JoanMarin>
# Copyright 2019 Diego Carvajak <Github@Diegoivanc>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models, fields, api, _
from odoo.tools.safe_eval import safe_eval
from odoo.exceptions import UserError
import logging
_logger = logging.getLogger(__name__)


class AccountInvoiceDebitNote(models.TransientModel):
    """Debit Note Invoice"""
    _name = "account.invoice.debit.note"
    _description = "Debit Note"

    @api.model
    def _get_reason(self):
        context = dict(self._context or {})
        active_id = context.get('active_id', False)
        if active_id:
            inv = self.env['account.move'].browse(active_id)
            return inv.name
        return ''

    date_invoice = fields.Date(
        string='Debit Note Date',
        default=fields.Date.context_today,
        required=True)
    date = fields.Date(string='Accounting Date')
    description = fields.Char(
        string='Reason',
        required=True,
        default=_get_reason)
    discrepancy_response_code_id = fields.Many2one(
        comodel_name='account.invoice.discrepancy.response.code',
        string='Correction concept for Refund Invoice')
    filter_debit_note = fields.Selection(
        [('debit', 'Create a draft debit note')],
        default='debit',
        string='Debit Note Method',
        required=True,
        help='Debit Note base on this type. You can not Modify and Cancel if the invoice is '
             'already reconciled')
    reason = fields.Char(string='Reason')

    @api.onchange('discrepancy_response_code_id')
    def _onchange_discrepancy_response_code_id(self):
        if self.discrepancy_response_code_id:
            self.description = self.discrepancy_response_code_id.name
    

    def reverse_moves(self):
        moves = self.env['account.move'].browse(self.env.context['active_ids']) if self.env.context.get('active_model') == 'account.move' else self.move_id

        # Create default values.
        default_values_list = []
        _logger.info('facturas')
        _logger.info('facturas')
        _logger.info('facturas')
        _logger.info('facturas')
        _logger.info(moves)
        for move in moves:
            _logger.info(move.invoice_line_ids)
            default_values_list.append({
                'ref': _('Reversal of: %s, %s') % (move.name, self.description) if self.description else _('Reversal of: %s') % (move.name),
                'date': self.date or move.date,
                'invoice_date': move.is_invoice(include_receipts=True) and (self.date or move.date) or False,
                #'journal_id': self.journal_id and self.journal_id.id or move.journal_id.id,
                'invoice_payment_term_id': None,
                #'auto_post': True if self.date > fields.Date.context_today(self) else False,
                'type': 'out_invoice_note',
                'refund_type': 'debit',
                'discrepancy_response_code_id': self.discrepancy_response_code_id.id,
                'payment_mean_id': move.payment_mean_id.id or False,
                'invoice_line_ids': move.invoice_line_ids

            })

        # Handle reverse method.
        new_moves = moves._reverse_movesnuevo(default_values_list)


        # Create action.
        action = {
            'name': _('Reverse Moves'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
        }
        if len(new_moves) == 1:
            action.update({
                'view_mode': 'form',
                'res_id': new_moves.id,
            })
        else:
            action.update({
                'view_mode': 'tree,form',
                'domain': [('id', 'in', new_moves.ids)],
            })
        return action

    def compute_debit_note(self, mode='debit'):
        msg1 = _('Cannot refund draft/proforma/cancelled invoice.')
        msg2 = _('Cannot refund invoice which is already reconciled, invoice should be '
                 'unreconciled first. You can only refund this invoice.')
        inv_obj = self.env['account.move']
        context = dict(self._context or {})
        xml_id = False

        for form in self:
            created_inv = []
            date = False
            description = False

            for inv in inv_obj.browse(context.get('active_ids')):
                if inv.state in ['draft', 'proforma2', 'cancel']:
                    raise UserError(msg1)

                if inv.has_reconciled_entries and mode in ('cancel', 'modify'):
                    raise UserError(msg2)

                date = form.date or False
                description = form.description or inv.name
                refund = inv.refund(form.date_invoice, date, description, inv.journal_id.id)
                refund.update({
                    'refund_type': 'debit',
                    'discrepancy_response_code_id': form.discrepancy_response_code_id.id,
                    'name': 'debit'})
                created_inv.append(refund.id)
                xml_id = (inv.type in ['out_refund', 'out_invoice']) and 'action_invoice_tree1' or \
                         (inv.type in ['in_refund', 'in_invoice']) and 'action_invoice_tree2'
                # Put the reason in the chatter
                subject = _("Debit Note Invoice")
                body = description
                refund.message_post(body=body, subject=subject)

        if xml_id:
            result = self.env.ref('account.%s' % (xml_id)).read()[0]
            invoice_domain = safe_eval(result['domain'])
            invoice_domain.append(('id', 'in', created_inv))
            result['domain'] = invoice_domain

            return result

        return True


    def _create_invoice(self, order, so_line, amount):
        if (self.advance_payment_method == 'percentage' and self.amount <= 0.00) or (self.advance_payment_method == 'fixed' and self.fixed_amount <= 0.00):
            raise UserError(_('The value of the down payment amount must be positive.'))
        if self.advance_payment_method == 'percentage':
            amount = order.amount_untaxed * self.amount / 100
            name = _("Down payment of %s%%") % (self.amount,)
        else:
            amount = self.fixed_amount
            name = _('Down Payment')

        invoice_vals = {
            'type': 'out_invoice',
            'invoice_origin': order.name,
            'invoice_user_id': order.user_id.id,
            'narration': order.note,
            'partner_id': order.partner_invoice_id.id,
            'fiscal_position_id': order.fiscal_position_id.id or order.partner_id.property_account_position_id.id,
            'partner_shipping_id': order.partner_shipping_id.id,
            'currency_id': order.pricelist_id.currency_id.id,
            'invoice_payment_ref': order.client_order_ref,
            'invoice_payment_term_id': order.payment_term_id.id,
            'invoice_partner_bank_id': order.company_id.partner_id.bank_ids[:1],
            'team_id': order.team_id.id,
            'campaign_id': order.campaign_id.id,
            'medium_id': order.medium_id.id,
            'source_id': order.source_id.id,
            'invoice_line_ids': [(0, 0, {
                'name': name,
                'price_unit': amount,
                'quantity': 1.0,
                'product_id': self.product_id.id,
                'product_uom_id': so_line.product_uom.id,
                'tax_ids': [(6, 0, so_line.tax_id.ids)],
                'sale_line_ids': [(6, 0, [so_line.id])],
                'analytic_tag_ids': [(6, 0, so_line.analytic_tag_ids.ids)],
                'analytic_account_id': order.analytic_account_id.id or False,
            })],
        }
        if order.fiscal_position_id:
            invoice_vals['fiscal_position_id'] = order.fiscal_position_id.id
        invoice = self.env['account.move'].sudo().create(invoice_vals).with_user(self.env.uid)
        invoice.message_post_with_view('mail.message_origin_link',
                    values={'self': invoice, 'origin': order},
                    subtype_id=self.env.ref('mail.mt_note').id)
        return invoice




    def invoice_debit_note(self):
        data_debit_note = self.read(['filter_debit_note'])[0]['filter_debit_note']

        return self.reverse_moves()


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    @api.onchange('quantity', 'discount', 'price_unit', 'tax_ids')
    def _onchange_price_subtotal(self):
        _logger.info('onchange prise sub')
        for line in self:
            _logger.info('onchange prise sub')
            _logger.info('onchange prise sub')
            _logger.info(line.move_id.is_invoice(include_receipts=True))
            if not line.move_id.is_invoice(include_receipts=True):
                continue

            line.update(line._get_price_total_and_subtotal())
            line.update(line._get_fields_onchange_subtotal())




class AccountMove(models.Model):
    _inherit = "account.move"

    type = fields.Selection(selection_add=[('out_invoice_note', 'Factura Nota Debito')])

    @api.model
    def get_invoice_types(self, include_receipts=False):
        return ['out_invoice','out_invoice_note', 'out_refund', 'in_refund', 'in_invoice'] + (
                    include_receipts and ['out_receipt', 'in_receipt'] or [])

    @api.model
    def get_inbound_types(self, include_receipts=True):
        return ['out_invoice','out_invoice_note', 'in_refund'] + (include_receipts and ['out_receipt'] or [])

    @api.model
    def get_sale_types(self, include_receipts=False):
        return ['out_invoice', 'out_invoice_note', 'out_refund'] + (include_receipts and ['out_receipt'] or [])

    def _get_creation_message(self):
        # OVERRIDE
        if not self.is_invoice(include_receipts=True):
            return super()._get_creation_message()
        return {
            'out_invoice': _('Invoice Created'),
            'out_invoice_note': _('Invoice Note Created'),
            'out_refund': _('Refund Created'),
            'in_invoice': _('Vendor Bill Created'),
            'in_refund': _('Credit Note Created'),
            'out_receipt': _('Sales Receipt Created'),
            'in_receipt': _('Purchase Receipt Created'),
        }[self.type]


    def _get_move_display_name(self, show_ref=False):
        ''' Helper to get the display name of an invoice depending of its type.
        :param show_ref:    A flag indicating of the display name must include or not the journal entry reference.
        :return:            A string representing the invoice.
        '''
        self.ensure_one()
        draft_name = ''
        if self.state == 'draft':
            draft_name += {
                'out_invoice': _('Draft Invoice'),
                'out_invoice_note': _('Draft Debit Note'),
                'out_refund': _('Draft Credit Note'),
                'in_invoice': _('Draft Bill'),
                'in_refund': _('Draft Vendor Credit Note'),
                'out_receipt': _('Draft Sales Receipt'),
                'in_receipt': _('Draft Purchase Receipt'),
                'entry': _('Draft Entry'),
            }[self.type]
            if not self.name or self.name == '/':
                draft_name += ' (* %s)' % str(self.id)
            else:
                draft_name += ' ' + self.name
        return (draft_name or self.name) + (show_ref and self.ref and ' (%s)' % self.ref or '')


    def refund(self, date_invoice=None, date=None, description=None, journal_id=None):
        new_invoices = self.browse()
        for invoice in self:
            # create the new invoice
            values = self._prepare_refund(invoice, date_invoice=date_invoice, date=date,
                                          description=description, journal_id=journal_id)
            refund_invoice = self.create(values)
            if invoice.type == 'out_invoice':
                message = _(
                    "This customer invoice credit note has been created from: <a href=# data-oe-model=account.invoice data-oe-id=%d>%s</a><br>Reason: %s") % (
                          invoice.id, invoice.number, description)
            else:
                message = _(
                    "This vendor bill credit note has been created from: <a href=# data-oe-model=account.invoice data-oe-id=%d>%s</a><br>Reason: %s") % (
                          invoice.id, invoice.number, description)

            refund_invoice.message_post(body=message)
            new_invoices += refund_invoice
        return new_invoices

    def _reverse_movesnuevo(self, default_values_list=None, cancel=False):
        ''' Reverse a recordset of account.move.
        If cancel parameter is true, the reconcilable or liquidity lines
        of each original move will be reconciled with its reverse's.

        :param default_values_list: A list of default values to consider per move.
                                    ('type' & 'reversed_entry_id' are computed in the method).
        :return:                    An account.move recordset, reverse of the current self.
        '''
        if not default_values_list:
            default_values_list = [{} for move in self]

        #if cancel:
        #    lines = self.mapped('line_ids')
            # Avoid maximum recursion depth.
        #    if lines:
        #        lines.remove_move_reconcile()

        reverse_type_map = {
            'entry': 'entry',
            'out_invoice': 'out_refund',
            'out_refund': 'entry',
            'in_invoice': 'in_refund',
            'in_refund': 'entry',
            'out_receipt': 'entry',
            'in_receipt': 'entry',
        }

        move_vals_list = []
        for move, default_values in zip(self, default_values_list):
            default_values.update({
                'type': 'out_invoice_note',
                'reversed_entry_id': move.id,
            })
            move_vals_list.append(move._reverse_move_valsnuevo(default_values, cancel=cancel))

        reverse_moves = self.env['account.move'].create(move_vals_list)


        return reverse_moves

    def _reverse_move_valsnuevo(self, default_values, cancel=True):
        ''' Reverse values passed as parameter being the copied values of the original journal entry.
        For example, debit / credit must be switched. The tax lines must be edited in case of refunds.

        :param default_values:  A copy_date of the original journal entry.
        :param cancel:          A flag indicating the reverse is made to cancel the original journal entry.
        :return:                The updated default_values.
        '''
        self.ensure_one()

        def compute_tax_repartition_lines_mapping2(move_vals):
            ''' Computes and returns a mapping between the current repartition lines to the new expected one.
            :param move_vals:   The newly created invoice as a python dictionary to be passed to the 'create' method.
            :return:            A map invoice_repartition_line => refund_repartition_line.
            '''
            # invoice_repartition_line => refund_repartition_line
            mapping = {}

            # Do nothing if the move is not a credit note.
            return mapping

        move_vals = self.with_context(include_business_fields=True).copy_data(default=default_values)[0]
        _logger.info('_reverse_move_valsnuevo')
        _logger.info(move_vals)
        _logger.info(default_values)

        tax_repartition_lines_mapping = compute_tax_repartition_lines_mapping2(move_vals)


        return move_vals
