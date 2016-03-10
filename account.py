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


class AccountImportContaplusStart(ModelView):
    'Account Import Contaplus Start'
    __name__ = 'account.import.contaplus.start'
    data = fields.Binary('File', required=True)

class AccountImportContaplus(Wizard):
    'Account Import Contaplus'
    __name__ = 'account.import.contaplus'
    start = StateView("account.import.contaplus.start",
                      'account_import_contaplus.account_import_contaplus_start_view_form',[
                          Button('Cancel', 'end', 'tryton-cancel'),
                          Button('Import', 'import_', 'tryton-ok', default=True)
                      ])
    import_ = StateTransition()

    def transition_import_(self):
        data_file = self.start.data

        pool = Pool()
        Account = pool.get('account.account')
        Move = pool.get('account.move')
        Line = pool.get('account.move.line')
        Period = pool.get('account.period')
        Journal = pool.get('account.journal')
        Party = pool.get('party.party')

        to_create = {}

        for iline in read(str(data_file)):

            if not iline.asien in to_create:
                move = Move()
                move.number = iline.asien
                move.date = iline.fecha
                move.period = Period.find(Transaction().context.get('company')
                                          , date= move.date )
                to_create[move.number] = move
                move.journal = Journal.search([('type', '=', 'general')], limit=1)[0]
                move.lines = []
                #todo check that move.number not in db already.

                # maybe add select journal to wizard fields
            else:
                move = to_create[move.number]

            line = Line()
            party = None
            account = iline.sub_cta.strip()
            if account[:2] in ('40', '41', '43'):
                party = account
                account = account[:2] + ('0' * 6)
            print ('lookup account# "%s"' % account)
            accounts = Account.search([('code', '=', account)], limit=1)
            if not accounts:
                print("missing account")
                continue
            # self.raise_user_error()
            line.account = accounts[0]
            if party:
                parties = Party.search([('rec_name', 'ilike', '%' + party)], limit=2)
                # todo limit 2 and check that we get only one.
                if (not parties) and (len(parties > 1)):
                    print("error party: %s" % party )
                    continue

                line.party = parties[0]
            line.debit = iline.euro_debe
            line.credit = iline.euro_haber
            # line.description =  u" ".join([iline.concepto, iline.documento])

            move.lines = move.lines + (line,)

            # move = Move()
            # move.post_date =
            # move.period =
            # move.journal =
            # move.description = ''
            # move.origin =
            # automatic? move.state =

            # line.debit??
            # line.credit??
            # line.party??
            # move.lines.append()

        print(" ############################## ready to save ###########################")
        if to_create:
            Move.save(to_create.values())
        print('click ok')
        return 'end'
