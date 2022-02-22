import logging
from retrofix.exception import RetrofixException
from retrofix.fields import Char, Date, Field, Integer
from retrofix.record import Record
from decimal import Decimal

from trytond.i18n import gettext
from trytond.exceptions import UserError
from trytond.model import ModelView, ModelSQL, fields
from trytond.pool import Pool, PoolMeta
from trytond.wizard import Wizard, StateTransition, StateView, Button
from trytond.transaction import Transaction
from functools import reduce

logger = logging.getLogger(__name__)


class DecimalField(Field):
    # decimals in files are separated by period '.'
    # have not implemented get_for_file because we only read.

    def __init__(self):
        super(DecimalField, self).__init__()

    def set_from_file(self, value):
        return Decimal(value)


ENTRY_RECORD = (
    (1, 6, 'asien', Char),
    (7, 8, 'fecha', Date('%Y%m%d')),
    (15, 12, 'sub_cta', Char),
    (27, 12, 'contra', Char),
    (39, 16, 'pta_debe', DecimalField),
    (55, 25, 'concepto', Char),
    (80, 16, 'pta_haber', DecimalField),
    (96, 8, 'factura', Char),  # Integer? it fails with some files if Integer.
    (104, 16, 'base_impo', DecimalField),
    (120, 5, 'iva', DecimalField),
    (125, 5, 'recequiv', DecimalField),
    (130, 10, 'documento', Char),
    (140, 3, 'departa', Char),
    (143, 6, 'clave', Char),
    (149, 1, 'estado', Char),
    (150, 6, 'n_casado', Integer),  # internal contaplus
    (156, 1, 't_casado', Integer),  # internal contaplus
    (157, 6, 'trans', Integer),
    (163, 16, 'cambio', DecimalField),
    (179, 16, 'debe_me', DecimalField),
    (195, 16, 'haber_me', DecimalField),
    (211, 1, 'auxiliar', Char),
    (212, 1, 'serie', Char),
    (213, 4, 'sucursal', Char),
    (217, 5, 'cod_divisa', Char),
    (222, 16, 'imp_aux_me', DecimalField),
    (238, 1, 'moneda_uso', Char),
    (239, 16, 'euro_debe', DecimalField),
    (255, 16, 'euro_haber', DecimalField),
    (271, 16, 'base_euro', DecimalField),
    (287, 1, 'no_conv', Char),  # internal contaplus
    (288, 10, 'numero_inv', Char))


def read_line(line):
    if Record.valid(line, ENTRY_RECORD):
        return Record.extract(line, ENTRY_RECORD)
    else:
        raise RetrofixException('Invalid record: %s' % line)


def read_all(data):
    return map(read_line, data.splitlines())


def filter_with_account(data):
    return filter((lambda s: len(s.sub_cta.strip()) != 0), data)


def read(data):
    return filter_with_account(read_all(data))


def add_tupla2(t1, t2):
    return (t1[0] + t2[0], t1[1] + t2[1])


def not_balance(move):
    credit_debit = reduce(
        lambda t_cd, line: add_tupla2(t_cd, (line.credit, line.debit)),
        move.lines, [0, 0])
    logger.info('credit %f, debit %f' % (credit_debit[0], credit_debit[1]))
    return credit_debit[0] != credit_debit[1]


def complete_account(account, num_digits, fill_with):
    ret = account
    while len(ret) < num_digits:
        ret = ret + fill_with
    return ret


def convert_account(account):
    # hack some accounts are not correct at import.
    # if more accounts appear consider using a map.
    if '4000' == account:
        return '40099999'
    else:
        return account


class Move(metaclass=PoolMeta):
    __name__ = 'account.move'

    @classmethod
    def _get_origin(cls):
        'Return list of Model names for origin Reference'
        return super(Move, cls)._get_origin() + ['import.record']


class Invoice(metaclass=PoolMeta):
    __name__ = 'account.invoice'

    @classmethod
    def _get_origin(cls):
        'Return list of Model names for origin Reference'
        return super(Invoice, cls)._get_origin() + ['import.record']


class ImportRecord(ModelSQL, ModelView):
    'Import Record'
    __name__ = 'import.record'
    _rec_name = 'filename'
    # filename
    filename = fields.Char('File Name')


class AccountImportContaplusStart(ModelView):
    'Account Import Contaplus Start'
    __name__ = 'account.import.contaplus.start'
    name = fields.Char('Name', states={'readonly': True}, required=True)
    data = fields.Binary(
        'File', filename='name', required=True, depends=['name'])
    is_invoice = fields.Boolean('Invoice?')
    journal = fields.Many2One('account.journal', 'Journal', required=True)

    @fields.depends('is_invoice')
    def on_change_is_invoice(self):
        journal_type = 'revenue' if self.is_invoice else 'general'
        Journal = Pool().get('account.journal')
        self.journal = Journal.search(
            [('type', "=", journal_type)], limit=1)[0].id

    @fields.depends('data')
    def on_change_data(self):
        inv = False
        if self.data:
            for iline in read_all(str(self.data, 'utf8')):
                if len(iline.contra.strip()) > 0:
                    inv = True
                    break
            self.is_invoice = inv
            self.on_change_is_invoice()

    @staticmethod
    def default_journal():
        Journal = Pool().get('account.journal')
        return Journal.search([('type', '=', 'general')], limit=1)[0].id


class AccountImportContaplus(Wizard):
    'Account Import Contaplus'
    __name__ = 'account.import.contaplus'
    start = StateView(
        "account.import.contaplus.start",
        'account_import_contaplus.account_import_contaplus_start_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'), Button(
                'Import', 'import_', 'tryton-ok', default=True)
        ])
    import_ = StateTransition()
    def get_party(self, party):
        logger.info(party)
        Party = Pool().get('party.party')
        parties = Party.search([('rec_name', 'ilike', '%' + party)], limit=2)
        if not parties:
            raise UserError(
                gettext('account_import_contaplus.msg_party_not_found' ,
                        party=party))
        if (len(parties) > 1):
            raise UserError(
                gettext('account_import_contaplus.msg_multiple_parties_found' ,
                        party=party))
        return parties[0]

    def get_account(self, account, company):
        Account = Pool().get('account.account')
        accounts = Account.search([('code', '=', account),
                                   ('company', '=', company)], limit=2)
        if not accounts:
            raise UserError(
                gettext('account_import_contaplus.msg_account_not_found' ,
                        account=account))
        if (len(accounts) > 1):
            raise UserError(
                gettext('account_import_contaplus.msg_multiple_accounts_found' ,
                        account=account))
        return accounts[0]

    def get_account_maybe(self, account, company):
        Account = Pool().get('account.account')
        accounts = Account.search([('code', '=', account),
                                   ('company', '=', company)], limit=2)
        if not accounts:
            return None
        if (len(accounts) > 1):
            return None
        return accounts[0]

    def import_moves(self, company, imp_record):
        pool = Pool()
        Move = pool.get('account.move')
        Line = pool.get('account.move.line')
        Period = pool.get('account.period')

        total_credit = 0
        total_debit = 0

        to_create = {}
        pre = "ALE-"
        for iline in read(str(self.start.data, 'utf8')):
            asien = pre + iline.asien

            if asien not in to_create:
                move = Move()
                move.origin = imp_record
                # move.origin_type =
                move.number = asien

                if len(Move.search(['number', '=', asien], limit=1)) > 0:
                    raise UserError(
                        gettext('account_import_contaplus.msg_number_exists' ,
                                move_number=asien))

                move.date = iline.fecha
                move.period = Period.find(company.id, date=move.date)
                to_create[move.number] = move
                move.journal = self.start.journal
                move.description = " ".join([iline.concepto, iline.documento])
                move.lines = []

            else:
                move = to_create[move.number]

            line = Line()
            party = None
            account = iline.sub_cta.strip()
            account = convert_account(account)

            account_maybe = self.get_account_maybe(account, company)
            party_required = (account_maybe is None) or \
                             (account_maybe.party_required)

            if party_required:
                party = company.party.code + '-' + account
                if (account[:2] in ('40', '41', '43')):
                    account = account[:2] + ('0' * 6)

            line.account = self.get_account(account, company)

            if party:
                line.party = self.get_party(party)

            logger.info('line account:' + account + 'requires party:' +
                        str(line.account.party_required) + 'party:' +
                        str(party))

            # swap debe haber in some cases due to error.
            # in caja the concepto/clave determines if it is debe or haber.
            if iline.concepto.strip() in (
                    '', 'TALON RTTE', 'CLAVE MANUAL', 'PAGO ITV', 'DESEMBOLSO',
                    'TRASP. A BAN', 'TRASP. A BANC', 'ANTICP-VALES'):
                line.debit = iline.euro_haber + iline.euro_debe
                line.credit = 0
            elif iline.concepto.strip() == 'cierre de caja':
                if (total_credit > total_debit):
                    line.debit = iline.euro_haber + iline.euro_debe
                    line.credit = 0
                else:
                    line.credit = iline.euro_haber + iline.euro_debe
                    line.debit = 0
            else:
                line.debit = iline.euro_debe
                line.credit = iline.euro_haber

            total_debit += line.debit
            total_credit += line.credit

            line.description = " ".join([iline.concepto, iline.documento])

            move.lines = move.lines + (line, )

        unbalance_moves = list(filter(not_balance, list(to_create.values())))
        if (unbalance_moves):
            raise UserError(
                gettext('account_import_contaplus.msg_unbalance_lines'))
        if to_create:
            Move.save(list(to_create.values()))
            Move.post(list(to_create.values()))
        # return created moves
        return to_create

    def check_totals(self, invoices, totals):
        for invoice in list(invoices.values()):
            if not invoice.total_amount == totals[invoice.number]:
                logger.info('unmatch total')
                logger.info(invoice.total_amount)
                logger.info(totals[invoice.number])
                for line in invoice.lines:
                    logger.info(line.unit_price)
                raise UserError(
                    gettext('account_import_contaplus.msg_unmatch_total_invoice' ,
                            invoice=invoice.number))
        return True

    def add_tax_invoice(self, invoice, vat, vat_21):
        for line in invoice.lines:
            # only add for lines that do not have taxes
            if len(line.taxes) == 0:
                line.taxes = [vat]

        invoice.sii_book_key = 'E'
        # TODO clientes contados should be F2 ticket
        invoice.sii_operation_key = 'F1'

        if vat == vat_21:
            invoice.sii_subjected_key = 'S1'
            invoice.sii_issued_key = '01'
        else:
            invoice.sii_excemption_key = 'E2'
            invoice.sii_issued_key = '02'
        return invoice


    def import_invoices(self, company, imp_record):
        pool = Pool()
        Invoice = pool.get('account.invoice')
        Line = pool.get('account.invoice.line')
        ModelData = pool.get('ir.model.data')
        Tax = pool.get('account.tax')

        logger.info("start import invoice")

        # TODO upgrade 4.7
        t_vat_21 = Tax(ModelData.get_id('account_es', 'iva_rep_21'))
        t_vat_0 = Tax(ModelData.get_id('account_es', 'iva_rep_ex'))
        vat_21, = Tax.search([('template', '=', t_vat_21),
                              ('company', '=', company)], limit=1)
        vat_0, = Tax.search([('template', '=', t_vat_0),
                             ('company', '=', company)], limit=1)

        to_create = {}
        vat = vat_0  # default vat no taxes
        totals = {}
        invoice = None  # current invoice
        for iline in read(str(self.start.data, 'utf8')):
            iline.factura = iline.factura.strip()
            iline.serie = iline.serie.strip()
            invoice_number = iline.serie + iline.factura
            if invoice_number not in to_create:
                # todo check num factura not alredy there.
                if invoice:
                    # check factura
                    # if lines empty remove from to_create
                    if len(invoice.lines) == 0:
                        del to_create[invoice.number]

                    self.add_tax_invoice(invoice, vat, vat_21)

                vat = vat_0  # default vat no taxes
                invoice = Invoice()
                invoice.company = company
                invoice.currency = company.currency
                invoice.origin = imp_record
                invoice.number = invoice_number
                invoice.invoice_date = iline.fecha
                invoice.type = 'out'
                invoice.journal = self.start.journal
                to_create[invoice.number] = invoice
                invoice.lines = []

            account = iline.sub_cta.strip()
            if account[:2] == '43':
                party_code = company.party.code + '-' + account
                party = self.get_party(party_code)

                if (party.customer_payment_term is None):
                    raise UserError(
                        gettext('account_import_contaplus.msg_missing_payment_term' ,
                                party=party.rec_name))

                invoice.party = party
                totals[invoice.number] = iline.euro_debe + iline.euro_haber
                # abonos negatius
                if iline.serie == 'A':
                    totals[invoice.number] = totals[invoice.number] * -1
                invoice.on_change_party()
                invoice.account = invoice.on_change_with_account()
                invoice.payment_term = invoice.on_change_with_payment_term()

            if account[:1] == '7' or account[:2] == '44':
                line = Line()
                line.account = self.get_account(iline.sub_cta.strip(), company)
                line.quantity = 1

                if iline.concepto.strip() == 'DIFERENCIA PORTE':
                    line.unit_price = iline.euro_haber * -1
                else:
                    line.unit_price = iline.euro_haber
                if iline.concepto.strip() == 'AVERIAS/FALTAS/R':
                    line.taxes = [vat_0]
                else:
                    line.taxes = []
                # abonos negatius
                if iline.serie == 'A':
                    line.unit_price = line.unit_price * -1
                line.description = iline.concepto.strip()
                invoice.lines = invoice.lines + (line, )

            if account[:3] == '477':
                vat = vat_21

        # todo duplicated code
        if invoice:
            # check factura
            # if lines empty remove from to_create
            if len(invoice.lines) == 0:
                del to_create[invoice.number]

            self.add_tax_invoice(invoice, vat, vat_21)

        if to_create:
            # recalculate invoice fields
            for k, invoice in list(to_create.items()):
                untaxed_amount = sum(line.quantity * line.unit_price
                    for line in invoice.lines if line.quantity)

                # set payment type
                if untaxed_amount > 0 and invoice.party.customer_payment_type:
                    invoice.payment_type = invoice.party.customer_payment_type
                    invoice._get_bank_account()
                elif untaxed_amount < 0 and invoice.party.supplier_payment_type:
                    invoice.payment_type = invoice.party.supplier_payment_type
                    invoice._get_bank_account()
                to_create[k] = invoice

            logger.info("save")
            Invoice.save(list(to_create.values()))
            logger.info("update_taxes")
            Invoice.update_taxes(list(to_create.values()))
            logger.info("check total")
            self.check_totals(to_create, totals)
            logger.info("post")
            #     logger.info("posting")
            #     logger.info(inv.number)
            #     logger.info(inv.party.name)
            #     logger.info(inv.party.customer_payment_term.name)
            #     logger.info(inv.payment_term.name)
            #     Invoice.post([inv])
            Invoice.post(list(to_create.values()))

        return to_create

    def create_import_record(self):
        pool = Pool()
        ImpRecord = pool.get('import.record')
        Attachment = pool.get('ir.attachment')

        imp_record = ImpRecord()
        imp_record.filename = self.start.name
        imp_record.save()

        attachment = Attachment()
        attachment.name = imp_record.filename
        attachment.resource = imp_record
        attachment.data = self.start.data
        attachment.save()

        return imp_record

    def transition_import_(self):
        pool = Pool()
        Company = pool.get('company.company')

        company_id = Transaction().context.get('company')
        company = Company(company_id)

        imp_record = self.create_import_record()

        if (self.start.is_invoice):
            self.import_invoices(company, imp_record)
        else:
            self.import_moves(company, imp_record)

        return 'end'
