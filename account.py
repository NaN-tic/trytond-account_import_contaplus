from retrofix.exception import RetrofixException
from retrofix.fields import Char, Date, Field, Integer
from retrofix.record import Record
from decimal import Decimal

from trytond.model import ModelView, ModelSQL, fields
from trytond.pool import Pool, PoolMeta
from trytond.wizard import Wizard, StateTransition, StateView, Button
from trytond.transaction import Transaction


__all__ = ['AccountImportContaplus', 'AccountImportContaplusStart',
           'ImportRecord', 'Move', 'Invoice']


class DecimalField(Field):
    # decimals in files are separated by period '.'
    # have not implemented get_for_file because we only read.

    def __init__(self):
        super(DecimalField, self).__init__()

    def set_from_file(self, value):
        return Decimal(value)


ENTRY_RECORD = (
    (1,6,'asien', Char),
    (7,8,'fecha', Date('%Y%m%d')),
    (15,12,'sub_cta', Char),
    (27,12,'contra', Char),
    (39,16,'pta_debe', DecimalField),
    (55,25,'concepto', Char),
    (80,16,'pta_haber', DecimalField),
    (96,8,'factura', Char), # Integer? it fails with some files if Integer.
    (104,16,'base_impo', DecimalField),
    (120,5,'iva', DecimalField),
    (125,5,'recequiv', DecimalField),
    (130,10,'documento', Char),
    (140,3,'departa', Char),
    (143,6,'clave', Char),
    (149,1,'estado', Char),
    (150,6,'n_casado', Integer),  # internal contaplus
    (156,1,'t_casado', Integer),  # internal contaplus
    (157,6,'trans', Integer),
    (163,16,'cambio', DecimalField),
    (179,16,'debe_me', DecimalField),
    (195,16,'haber_me', DecimalField),
    (211,1,'auxiliar', Char),
    (212,1,'serie', Char),
    (213,4,'sucursal', Char),
    (217,5,'cod_divisa', Char),
    (222,16,'imp_aux_me', DecimalField),
    (238,1,'moneda_uso', Char),
    (239,16,'euro_debe', DecimalField),
    (255,16,'euro_haber', DecimalField),
    (271,16,'base_euro', DecimalField),
    (287,1,'no_conv', Char),  # internal contaplus
    (288,10,'numero_inv', Char)
    )


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
        lambda t_cd, line:
        add_tupla2(t_cd, (line.credit, line.debit)),
        move.lines,
        [0,0])
    print (move.number)
    print (credit_debit)
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


class Move:
    __name__ = 'account.move'
    # seach this 'class' account.move in the list of register entities in Pool.
    __metaclass__ = PoolMeta

    @classmethod
    def _get_origin(cls):
        'Return list of Model names for origin Reference'
        return super(Move, cls)._get_origin() +  ['import.record']


class Invoice:
    __name__ = 'account.invoice'
    __metaclass__ = PoolMeta

    @classmethod
    def _get_origin(cls):
        'Return list of Model names for origin Reference'
        return super(Invoice, cls)._get_origin() +  ['import.record']


class ImportRecord(ModelSQL, ModelView):
    'Import Record'
    __name__ = 'import.record'
    _rec_name = 'filename'
    # filename
    filename = fields.Char('File Name')


class AccountImportContaplusStart(ModelView):
    'Account Import Contaplus Start'
    __name__ = 'account.import.contaplus.start'
    name = fields.Char('Name', states={'read only': True}, required=True)
    data = fields.Binary('File', filename='name', required=True,
                         depends=['name'])
    is_invoice = fields.Boolean('Invoice?')
    journal = fields.Many2One('account.journal', 'Journal', required=True)

    @fields.depends('is_invoice')
    def on_change_is_invoice(self):
        journal_type = 'revenue' if self.is_invoice else 'general'
        Journal = Pool().get('account.journal')
        self.journal = Journal.search([('type', "=", journal_type)],
                                      limit=1)[0].id

    @fields.depends('data')
    def on_change_data(self):
        print("change data")
        inv = False
        for iline in read_all(str(self.data)):
            if len(iline.contra.strip()) > 0:
                inv = True
                break
        # print(inv)
        self.is_invoice = inv
        self.on_change_is_invoice()

    @staticmethod
    def default_journal():
        Journal = Pool().get('account.journal')
        return Journal.search([('type', '=', 'general')], limit=1)[0].id


class AccountImportContaplus(Wizard):
    'Account Import Contaplus'
    __name__ = 'account.import.contaplus'
    start = StateView("account.import.contaplus.start",
                      'account_import_contaplus.account_import_contaplus_start_view_form',[
                          Button('Cancel', 'end', 'tryton-cancel'),
                          Button('Import', 'import_', 'tryton-ok', default=True)
                      ])
    import_ = StateTransition()

    @classmethod
    def __setup__(cls):
        super(AccountImportContaplus, cls).__setup__()
        cls._error_messages.update({
            'number exists': ('Duplicated account move number "%(move_number)s".'),
            'account not found': ('Account "%(account)s" not found '),
            'multiple accounts found' : ('Multiple accounts fount for "%(account)s"'),
            'party not found': ('Party "%(party)s" not found '),
            'multiple parties found' : ('Multiple parties fount for "%(party)s"'),
            'unbalance lines': ('Unbalance lines'),
            'unmatch total invoice': ('Total for %(invoice)s does not match')
        })

    def get_party(self, party):
        Party = Pool().get('party.party')
        parties = Party.search([('rec_name', 'ilike', '%' + party)], limit=2)
        if not parties:
            self.raise_user_error('party not found', {'party': party})
        if (len(parties) > 1):
            self.raise_user_error('multiple parties found', {'party': party})
        return parties[0]

    def get_account(self, account):
        Account = Pool().get('account.account')
        accounts = Account.search([('code', '=', account)], limit=2)
        if not accounts:
            self.raise_user_error('account not found', {'account': account})
        if (len(accounts) > 1):
            self.raise_user_error('multiple accounts found',
                                  {'account': account})
        return accounts[0]

    def import_moves(self, company, imp_record):
        pool = Pool()
        Move = pool.get('account.move')
        Line = pool.get('account.move.line')
        Period = pool.get('account.period')

        to_create = {}
        pre = "ALE-"
        for iline in read(str(self.start.data)):
            asien = pre + iline.asien

            if asien not in to_create:
                move = Move()
                move.origin = imp_record
                # move.origin_type =
                move.number = asien

                if len(Move.search(['number', '=', move.number], limit=1)) > 0:
                    self.raise_user_error('number exists',
                                          {'move_number': move.number})

                move.date = iline.fecha
                move.period = Period.find(company.id, date=move.date)
                to_create[move.number] = move
                move.journal = self.start.journal
                move.lines = []

            else:
                move = to_create[move.number]

            line = Line()
            party = None
            account = iline.sub_cta.strip()
            account = convert_account(account)
            if account[:2] in ('40', '41', '43'):
                party = company.party.code + '-' + account
                account = account[:2] + ('0' * 6)

            line.account = self.get_account(account)
            if party:
                line.party = self.get_party(party)

            # swap debe haber in some cases due to error.
            # in caja the concepto/clave determines if it is debe or haber.
            if iline.concepto.strip() in ('',
                                        'TALON RTTE',
                                        'CLAVE MANUAL',
                                        'PAGO ITV',
                                        'DESEMBOLSO',
                                        'TRASP. A BANC',
                                        'ANTICP-VALES'):
                line.debit = iline.euro_haber + iline.euro_debe
                line.credit = 0
            else:
                line.debit = iline.euro_debe
                line.credit = iline.euro_haber

            line.description = " ".join([iline.concepto, iline.documento])

            move.lines = move.lines + (line,)

        unbalance_moves = filter(not_balance, to_create.values())
        if (unbalance_moves):
            self.raise_user_error('unbalance lines')
        if to_create:
            Move.save(to_create.values())
        # return created moves
        return to_create

    def check_totals(self, invoices, totals):
        for invoice in invoices.values():
            if not invoice.total_amount == totals[invoice.number]:
                self.raise_user_error('unmatch total invoice',
                                      {'invoice': invoice.number})
        return True

    def add_tax_invoice(self, invoice, vat):
        for line in invoice.lines:
            line.taxes = [vat]
        return invoice

    def import_invoices(self, company, imp_record):

        pool = Pool()
        Invoice = pool.get('account.invoice')
        Line = pool.get('account.invoice.line')

        ModelData = pool.get('ir.model.data')
        Tax = pool.get('account.tax')

        t_vat_21 = Tax(ModelData.get_id('account_es', 'iva_rep_21'))
        t_vat_0 = Tax(ModelData.get_id('account_es', 'iva_rep_ex'))
        vat_21, = Tax.search([('template', '=', t_vat_21)], limit=1)
        vat_0, = Tax.search([('template', '=', t_vat_0)], limit=1)

        to_create = {}
        vat = vat_0   # default vat no taxes
        totals = {}
        invoice = None   # current invoice
        for iline in read(str(self.start.data)):
            iline.factura = iline.factura.strip()
            if iline.factura not in to_create:
                # todo check num factura not alredy there.
                if invoice:
                    # check factura
                    # if lines empty remove from to_create
                    if len(invoice.lines) == 0:
                        del to_create[invoice.number]



                    self.add_tax_invoice(invoice, vat)

                vat = vat_0   # default vat no taxes
                invoice = Invoice()
                invoice.company = company
                invoice.currency = company.currency
                invoice.origin = imp_record
                invoice.number = iline.factura
                invoice.invoice_date = iline.fecha
                invoice.type = 'out_invoice'
                invoice.journal = self.start.journal
                to_create[invoice.number] = invoice
                invoice.lines = []

            account = iline.sub_cta.strip()
            if account[:2] == '43':
                party = company.party.code + '-' + account
                # print(party)
                # print(Transaction().context.get('company'))
                invoice.party = self.get_party(party)
                # print(invoice.party.id)
                totals[invoice.number] = iline.euro_debe
                invoice.on_change_party()

            if account[:1] == '7' or account[:2] == '44':
                line = Line()
                line.account = self.get_account(iline.sub_cta.strip())
                line.quantity = 1
                line.unit_price = iline.euro_haber
                line.description = iline.concepto
                invoice.lines = invoice.lines + (line,)

            if account[:3] == '477':
                vat = vat_21

            # total factura
            # invoice.total_amount  # check against 430
            # total tax
            # invoice.tax_amount # check if wanted against 477

        # todo duplicated code
        if invoice:
            # check factura
            # if lines empty remove from to_create
            if len(invoice.lines) == 0:
                del to_create[invoice.number]

            self.add_tax_invoice(invoice, vat)

        if to_create:
            Invoice.save(to_create.values())
            Invoice.update_taxes(to_create.values())

        self.check_totals(to_create,totals)

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
        data_file = self.start.data

        # print(self.start.name)
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
