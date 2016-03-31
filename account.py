from retrofix.exception import RetrofixException
from retrofix.fields import *
from retrofix.record import Record
from decimal import Decimal


from trytond.model import ModelView, fields
from trytond.pool import Pool
from trytond.wizard import Wizard, StateTransition, StateView, Button
from trytond.transaction import Transaction


__all__ = ['AccountImportContaplus', 'AccountImportContaplusStart']


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


class AccountImportContaplusStart(ModelView):
    'Account Import Contaplus Start'
    __name__ = 'account.import.contaplus.start'
    data = fields.Binary('File', required=True)
    journal = fields.Many2One('account.journal', 'Journal', required=True)

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
            'unbalance lines': ('Unbalance lines')
        })

    def transition_import_(self):
        data_file = self.start.data

        print(type(self.start.data))

        companyId = Transaction().context.get('company')

        pool = Pool()
        Company = pool.get('company.company')
        Account = pool.get('account.account')
        Move = pool.get('account.move')
        Line = pool.get('account.move.line')
        Period = pool.get('account.period')
        Party = pool.get('party.party')

        company = Company.search(['id', '=', companyId], limit=1)[0]
        company_party_code = company.party.code

        to_create = {}

        for iline in read(str(data_file)):

            if not iline.asien in to_create:
                move = Move()
                move.number = iline.asien

                if len(Move.search(['number', '=', move.number], limit=1)) > 0:
                    self.raise_user_error('number exists',
                                          {'move_number' : move.number})

                move.date = iline.fecha
                move.period = Period.find(companyId
                                          , date= move.date )
                to_create[move.number] = move
                move.journal = self.start.journal
                move.lines = []

            else:
                move = to_create[move.number]

            line = Line()
            party = None
            account = iline.sub_cta.strip()
            account = convert_account(account)
            if account[:2] in ('40', '41', '43', '44'):
                party = company_party_code + '-' + account
                account = account[:2] + ('0' * 6)

            accounts = Account.search([('code', '=', account)], limit=2)
            if not accounts:
                self.raise_user_error('account not found', {'account': account})
            if (len(accounts) > 1):
                self.raise_user_error('multiple accounts found', {'account': account})
            line.account = accounts[0]
            if party:
                parties = Party.search([('rec_name', 'ilike', '%' + party)], limit=2)
                if not parties:
                    self.raise_user_error('party not found', {'party': party})
                if (len(parties) > 1):
                    self.raise_user_error('multiple parties found', {'party': party})
                line.party = parties[0]

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
        return 'end'
